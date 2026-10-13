#!/usr/bin/env python3
"""Independent warm-once/profile-once memory experiment; never updates runtime results.

Operator observations sample the *shared database buffer pool* at EndOperator.
Round peaks use MAX, are not exclusive allocations, and must not be added.
Linux RSS is sampled separately during the measured execution (not the warmup).
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "auto_test/outerjoin_benchmark/benchmark"
DEFAULT_COHORT = ROOT / "auto_test/memory_cohort_20261013.json"
MEMORY = "system_peak_buffer_memory"
SPILL = "system_peak_temp_dir_size"
PHASES = ("round1", "round2", "round3", "other")
JOINS = {"BLOCKWISE_NL_JOIN", "NESTED_LOOP_JOIN", "HASH_JOIN", "CROSS_PRODUCT",
         "PIECEWISE_MERGE_JOIN", "IE_JOIN", "LEFT_DELIM_JOIN", "RIGHT_DELIM_JOIN",
         "POSITIONAL_JOIN", "ASOF_JOIN"}
EXPECTED_COUNTS = dict(graph=47, tpch=80, tpcds=45, job=109)
FAMILIES = {"Graph": "graph", "SGPB": "graph", "TPC-H": "tpch", "TPC-DS": "tpcds", "JOB": "job"}
PROTOCOL = "memory-warm1-profile1-v1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def prepare(stats_path, output):
    stats = json.loads(stats_path.read_text())
    with (CORPUS / "manifest.csv").open(newline="") as handle:
        manifest = {r["query_id"]: r for r in csv.DictReader(handle)}
    records = []
    for q in stats["queries"]:
        if not (q["selected_plan"] == "OUTERYAN" and q["valid_timing"]
                and q["runtime_treatment"] == "measured" and q["timing_status"] == "measured"):
            raise ValueError("Cohort must contain only complete selected measured pairs")
        row = manifest[q["query"]]
        if row["path"] != q["sql_path"] or row["family"] != FAMILIES[q["family"]]:
            raise ValueError("Statistics/active manifest identity mismatch")
        if row["sql_fingerprint"] != q["sql_identity"]:
            raise ValueError("Statistics refer to a different SQL identity: " + q["query"])
        records.append(dict(query=row["query_id"], family=row["family"], sql_path=row["path"],
                            sql_sha256=row["content_sha256"], graph_dataset=q.get("graph_dataset", ""),
                            reference_off_s=q["off_s"], reference_on_s=q["on_s"]))
    cohort = dict(protocol=PROTOCOL, statistics_sha256=digest(stats_path),
                  manifest_sha256=digest(CORPUS / "manifest.csv"), active_query_count=len(manifest),
                  family_counts=dict(Counter(r["family"] for r in records)), queries=records)
    validate(cohort)
    if output.exists():
        raise ValueError("Refusing to overwrite an existing cohort")
    write_json(output, cohort)
    print("Pinned {} SQL identities: {}".format(len(records), cohort["family_counts"]))


def validate(cohort):
    if cohort["protocol"] != PROTOCOL or cohort["active_query_count"] != 720:
        raise ValueError("Unexpected cohort protocol or benchmark size")
    if digest(CORPUS / "manifest.csv") != cohort["manifest_sha256"]:
        raise ValueError("Active benchmark changed; do not silently rebase memory cohort")
    rows = cohort["queries"]
    if len(rows) != 281 or len({q["query"] for q in rows}) != 281:
        raise ValueError("Expected exactly 281 distinct query identities")
    if Counter(q["family"] for q in rows) != EXPECTED_COUNTS:
        raise ValueError("Unexpected family counts")
    for q in rows:
        path = Path(q["sql_path"])
        if path.parts != (q["family"], q["query"] + ".sql"):
            raise ValueError("Unsafe or mismatching query path")
        if digest(CORPUS / path) != q["sql_sha256"]:
            raise ValueError("SQL changed: " + str(path))
        if q["family"] == "graph" and q["graph_dataset"] not in ("bitcoin", "epinions"):
            raise ValueError("Missing Graph dataset identity")


def phase(node):
    name = str(node.get("operator_name", "")).strip().upper()
    if name in ("SJ_BUILD_ROUND_1", "SJ_PROBE_ROUND_1"):
        return "round1"
    if name in ("SJ_BUILD_ROUND_2", "SJ_PROBE_ROUND_2"):
        return "round2"
    if name in JOINS or str(node.get("operator_type", "")).upper() in JOINS:
        return "round3"
    return "other"


def normalize(sql):
    # Used only for checking our generated corpus's profile query_name.
    return " ".join(re.sub(r"--[^\n]*", "", sql).strip().rstrip(";").split())


def profile_metrics(root, sql):
    if normalize(root.get("query_name", "")) != normalize(sql):
        raise ValueError("Profile belongs to a different query")
    for key in (MEMORY, SPILL, "latency"):
        if key not in root or not math.isfinite(float(root[key])) or float(root[key]) < 0:
            raise ValueError("Missing/invalid query metric: " + key)
    operators = []

    def visit(node):
        for child in node.get("children", []):
            for key in (MEMORY, SPILL):
                if key not in child or not math.isfinite(float(child[key])) or child[key] < 0:
                    raise ValueError("Missing/invalid operator memory observation")
                if child[key] > root[key]:
                    raise ValueError("Operator observation exceeds query peak")
            operators.append(dict(name=child.get("operator_name", ""), phase=phase(child),
                                  buffer_peak_bytes=int(child[MEMORY]), spill_peak_bytes=int(child[SPILL]),
                                  operator_time_s=child.get("operator_timing", 0)))
            visit(child)
    visit(root)
    if not operators:
        raise ValueError("No operator tree in profile")
    # Older builds write zero for all child memory metrics. Reject instead of
    # producing plausible-looking zero-valued round statistics.
    if max(o["buffer_peak_bytes"] for o in operators) != root[MEMORY]:
        raise ValueError("Operator memory peaks missing/stale; rebuild with memory profiling patch")
    if max(o["spill_peak_bytes"] for o in operators) != root[SPILL]:
        raise ValueError("Operator spill peaks missing/stale")
    groups = {}
    for key in PHASES:
        ops = [o for o in operators if o["phase"] == key]
        groups[key] = dict(operator_count=len(ops),
                           buffer_peak_bytes=max((o["buffer_peak_bytes"] for o in ops), default=None),
                           spill_peak_bytes=max((o["spill_peak_bytes"] for o in ops), default=None))
    return dict(buffer_peak_bytes=int(root[MEMORY]), spill_peak_bytes=int(root[SPILL]),
                profiled_wall_s=root["latency"], phases=groups, operators=operators)


def sql_literal(text):
    return "'" + str(text).replace("'", "''") + "'"


def session_sql(sql, engine, profile_path, threads, timeout):
    bare = sql.strip().rstrip(";") + ";\n"
    disabled = "outer_yan" if engine == "duckdb" else ""
    return (".bail on\n.mode trash\nCALL disable_profiling();\n"
            "SET threads={}; SET max_execution_time={};\n"
            "SET disabled_optimizers={}; SET enable_progress_bar=false;\n"
            ".print OY_MEMORY_STAGE=warmup\n{}"
            ".print OY_MEMORY_STAGE=measure\n"
            "CALL enable_profiling(format='json', save_location={}, coverage='select');\n{}"
            "PRAGMA disable_profiling;\n.print OY_MEMORY_STAGE=done\n").format(
                threads, timeout * 1000, sql_literal(disabled), bare, sql_literal(profile_path), bare)


def read_rss(pid):
    try:
        for line in Path("/proc/{}/status".format(pid)).read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return None


def run_side(binary, db, sql, engine, prefix, threads, timeout):
    profile = prefix.with_suffix(".profile.json")
    trace = prefix.with_suffix(".trace")
    sql_file = prefix.with_suffix(".sql")
    sql_file.write_text(session_sql(sql, engine, profile, threads, timeout))
    env = os.environ.copy()
    for key in ("DUCKDB_OYTRACE", "DUCKDB_SJ_KERNEL_TRACE", "DUCKDB_OY_TRACE", "DUCKDB_OY_KERNEL_TRACE"):
        env.pop(key, None)
    env["DUCKDB_OY_PROFILE_TRACE"] = str(trace)
    started = time.monotonic()
    stage, pending, output = "setup", b"", []
    rss_peak, rss_samples, watchdog = None, 0, False
    stages = []
    with sql_file.open() as source, prefix.with_suffix(".log").open("wb") as log:
        proc = subprocess.Popen([str(binary), "-readonly", "-no-init", "-bail", str(db)],
                                stdin=source, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=env, start_new_session=True)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                # SQL timeout is per execution; this guard is for a hung client,
                # not a shared budget for warmup and measurement.
                if not watchdog and time.monotonic() - started > 2 * timeout + 60:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                    watchdog = True
                if stage == "measure":
                    rss = read_rss(proc.pid)
                    if rss is not None:
                        rss_peak = max(rss_peak or 0, rss)
                        rss_samples += 1
                for key, _ in selector.select(0.05):
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    log.write(data)
                    log.flush()
                    output.append(data)
                    pending += data
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if line.startswith(b"OY_MEMORY_STAGE="):
                            stage = line.decode().split("=", 1)[1].strip()
                            stages.append(stage)
                            print("      {}: {}".format(engine, stage), flush=True)
            code = proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            selector.close()
            proc.stdout.close()
    text = b"".join(output).decode(errors="replace")
    result = dict(engine=engine, status="error", stage=stage, exit_code=code,
                  session_wall_s=time.monotonic() - started, warmups_completed=int("measure" in stages),
                  measured_executions_completed=int("done" in stages), timeout_seconds=timeout,
                  measured_rss_sampled_peak_bytes=rss_peak, measured_rss_samples=rss_samples,
                  profile_path=str(profile), log_path=str(prefix.with_suffix(".log")))
    if watchdog or (code != 0 and re.search(r"timeout|timed out|interrupted", text, re.I)):
        result["status"] = "timeout"
    elif code == 0 and stages == ["warmup", "measure", "done"]:
        try:
            result.update(profile_metrics(json.loads(profile.read_text()), sql))
            result["status"] = "ok"
            if engine == "outeryan":
                decisions = [s for s in trace.read_text().splitlines() if s.startswith("[OY_DECISION]")]
                if len(decisions) != 1:
                    raise ValueError("Expected one profiled OuterYan decision")
                fields = dict(token.split("=", 1) for token in decisions[0].split()[1:] if "=" in token)
                result["decision"] = fields
                result["selected"] = fields.get("outer_yan_selected") == "1"
                if not result["selected"]:
                    result["status"] = "not_selected"
        except (OSError, ValueError, KeyError) as error:
            result.update(status="profile_error", error=str(error))
    else:
        result["error"] = text[-2000:]
    return result


def sql_json(binary, db, sql):
    command = "SET disabled_optimizers='outer_yan'; SET max_execution_time=60000; " + sql
    result = subprocess.run([str(binary), "-readonly", "-no-init", "-bail", "-json", str(db), "-c", command],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                            timeout=90, check=True)
    return json.loads(result.stdout)


def verify_databases(binary, databases):
    evidence = {}
    for key, path in databases.items():
        if not path.is_file():
            raise ValueError("Existing database required: " + str(path))
        st = path.stat()
        evidence[key] = dict(path=str(path), size_bytes=st.st_size, mtime_ns=st.st_mtime_ns)
    checks = dict(tpch=("SELECT (SELECT count(*) FROM orders) AS orders, "
                       "(SELECT count(*) FROM customer) AS customer", dict(orders=75000000, customer=7500000)),
                  tpcds=("SELECT count(*) AS n FROM store_sales", dict(n=144004764)))
    for key, (sql, expected) in checks.items():
        actual = sql_json(binary, databases[key], sql)[0]
        if actual != expected:
            raise ValueError("SF50 identity mismatch for {}: {}".format(key, actual))
        evidence[key]["counts"] = actual
    for key, expected in (("bitcoin", 24186), ("epinions", 508837)):
        counts = sql_json(binary, databases[key], "SELECT " + ",".join(
            "(SELECT count(*) FROM R{}) AS r{}".format(i, i) for i in range(1, 6)))[0]
        if set(counts.values()) != {expected}:
            raise ValueError("Graph dataset identity mismatch: {} {}".format(key, counts))
        evidence[key]["counts"] = counts
        signature = sql_json(binary, databases[key],
                             "SELECT sum(src)::VARCHAR AS src, sum(dst)::VARCHAR AS dst FROM R1")[0]
        expected_signature = dict(src="20897413", dst="25421755") if key == "bitcoin" else dict(
            src="6077109843", dst="5363312929")
        if signature != expected_signature:
            raise ValueError("Graph edge signature mismatch: " + key)
        evidence[key]["edge_signature"] = signature
    evidence["job"]["counts"] = sql_json(binary, databases["job"], "SELECT count(*) AS title FROM title")[0]
    evidence["settings"] = sql_json(binary, databases["tpch"],
                                    "SELECT current_setting('memory_limit') AS memory_limit")
    return evidence


def summarize(records):
    groups = {}
    for family in list(EXPECTED_COUNTS) + ["all"]:
        subset = [r for r in records if family == "all" or r["family"] == family]
        valid = [r for r in subset if all(r[e]["status"] == "ok" for e in ("duckdb", "outeryan"))]
        group = dict(attempted=len(subset), valid_pairs=len(valid), excluded=len(subset) - len(valid))
        for engine in ("duckdb", "outeryan"):
            values = [r[engine]["buffer_peak_bytes"] / 2**20 for r in valid]
            group[engine] = dict(median_buffer_peak_mib=statistics.median(values) if values else None,
                                 max_buffer_peak_mib=max(values) if values else None,
                                 statuses=dict(Counter(r[engine]["status"] for r in subset)))
        for p in PHASES:
            values = [r["outeryan"]["phases"][p]["buffer_peak_bytes"] for r in valid]
            values = [v / 2**20 for v in values if v is not None]
            group[p] = dict(queries_with_operators=len(values),
                            median_observed_buffer_peak_mib=statistics.median(values) if values else None,
                            max_observed_buffer_peak_mib=max(values) if values else None)
        groups[family] = group
    return dict(protocol=PROTOCOL, units="MiB (2^20 bytes)", groups=groups,
                rule="Complete measured pairs with OuterYan selected; exclude either-engine timeout/error. "
                     "Round memory uses MAX of shared buffer-pool observations at operator boundaries, "
                     "not owned allocations. Phases overlap in lifetime and must not be added. "
                     "Missing round operators are null, not zero. RSS is separately sampled every 50ms "
                     "during measurement only and can miss short peaks. Spill is disk usage, not RAM. "
                     "Profiled wall time does not replace five-run unprofiled runtime medians.")


def run(args):
    cohort = json.loads(args.cohort.read_text())
    validate(cohort)
    binary = args.bin.resolve(strict=True)
    databases = {k: (args.db_root / name).resolve() for k, name in dict(
        tpch="tpch_50.duckdb", tpcds="tpcds_50.duckdb", job="job_db", bitcoin="graph_db",
        epinions="graph_epinions.duckdb").items()}
    evidence = verify_databases(binary, databases)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "profiles").mkdir()
    write_json(out / "cohort.json", cohort)
    print("Checking that the Release binary exports per-operator memory observations...", flush=True)
    smoke = run_side(binary, databases["bitcoin"], "SELECT sum(src) FROM R1;", "duckdb",
                     out / "profiles/preflight", args.threads, 60)
    write_json(out / "preflight.json", smoke)
    if smoke["status"] != "ok" or smoke.get("buffer_peak_bytes", 0) == 0:
        raise ValueError("Memory profiler preflight failed; rebuild before running the cohort: " + repr(smoke))
    write_json(out / "run.json", dict(protocol=PROTOCOL, host=socket.gethostname(), threads=args.threads,
               timeout_seconds_per_execution=args.timeout, correctness_check=False,
               warmups_per_engine=1, measurements_per_engine=1, cohort_sha256=digest(args.cohort),
               binary_sha256=digest(binary), binary=str(binary), database_verification=evidence,
               git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT)).decode().strip()))
    records = []
    with (out / "queries.jsonl").open("x") as journal:
        for index, query in enumerate(cohort["queries"], 1):
            print("\n[{}/281] {} {}".format(index, query["family"], query["query"]), flush=True)
            path = CORPUS / query["sql_path"]
            if digest(path) != query["sql_sha256"]:
                raise ValueError("SQL changed during experiment")
            db_key = query["graph_dataset"] if query["family"] == "graph" else query["family"]
            row = dict(query)
            row["engines_in_order"] = ["duckdb", "outeryan"] if index % 2 else ["outeryan", "duckdb"]
            for engine in row["engines_in_order"]:
                prefix = out / "profiles" / "{:03d}_{}".format(index, engine)
                row[engine] = run_side(binary, databases[db_key], path.read_text(), engine,
                                       prefix, args.threads, args.timeout)
                print("    {}: {} buffer_peak={} MiB, RSS={} MiB".format(
                    engine, row[engine]["status"],
                    round(row[engine]["buffer_peak_bytes"] / 2**20, 3) if "buffer_peak_bytes" in row[engine] else "NA",
                    round(row[engine]["measured_rss_sampled_peak_bytes"] / 2**20, 3)
                    if row[engine]["measured_rss_sampled_peak_bytes"] is not None else "NA"), flush=True)
            records.append(row)
            journal.write(json.dumps(row, sort_keys=True) + "\n")
            journal.flush()
            os.fsync(journal.fileno())
            write_json(out / "summary.json", summarize(records))
    print("MEMORY_RESULT_DIR=" + str(out), flush=True)
    print("CPU9_MEMORY_EXIT=0", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--statistics", type=Path, required=True)
    p.add_argument("--out", type=Path, default=DEFAULT_COHORT)
    p = sub.add_parser("validate")
    p.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    p = sub.add_parser("run")
    p.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    p.add_argument("--bin", type=Path, default=ROOT / "build/release/duckdb")
    p.add_argument("--db-root", type=Path, default=ROOT)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--threads", type=int, default=32)
    p.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.statistics, args.out)
    elif args.command == "validate":
        validate(json.loads(args.cohort.read_text()))
        print("Validated 281 current selected SQL identities")
    else:
        if args.threads < 1 or args.timeout < 1:
            parser.error("threads and timeout must be positive")
        run(args)


if __name__ == "__main__":
    main()
