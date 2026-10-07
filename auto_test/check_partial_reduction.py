#!/usr/bin/env python3
"""Diagnose current measured regressions with partial reduction OFF versus ON.

Default: EXPLAIN only, under the normal cost gate. --execute additionally runs
the bare SELECT once for warm-up and once for timing per mode, without profiling
or trace overhead. These diagnostic timings do NOT verify result equivalence.
Never builds databases, regenerates queries, or edits original measurements.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile

from benchmark_corpus import SQL_TOKEN
from database_paths import database_path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "auto_test/outerjoin_benchmark/benchmark"
FAMILIES = {"graph": "graph", "tpch": "tpch", "tpc-h": "tpch",
            "tpcds": "tpcds", "tpc-ds": "tpcds", "job": "job"}
COUNTS = ("round1_pairs", "round1_filters", "round2_pairs", "round2_filters")
UNSAFE_ENV = ("FORCE", "DUCKDB_OY_FORCE_CANDIDATE", "DUCKDB_OY_SIMPLIFY_SCAN_FILTERS",
              "DUCKDB_OYTRACE", "DUCKDB_OY_PROFILE_TRACE", "DUCKDB_SJ_KERNEL_TRACE")
TIMER = re.compile(r"(?m)^Run Time(?: \(s\))?: real\s+([0-9]+(?:\.[0-9]*)?(?:[eE][+-]?\d+)?)")


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_cohort(csv_path, threshold=0.8, families=None, limit=None, corpus=CORPUS):
    """Use measured pairs only, including subsecond pairs; pin to active SQL."""
    with (corpus / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        manifest = {row["path"]: row for row in csv.DictReader(handle)}
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        source = list(csv.DictReader(handle))
    cohort, seen = [], set()
    for row in source:
        off, on = number(row.get("tm_off")), number(row.get("tm_on"))
        correct = row.get("correct", "").upper()
        eligible_correct = correct == "TRUE" or (
            correct == "NOT-CHECKED" and row.get("correctness_check", "").lower() == "disabled")
        if (not eligible_correct or row.get("timing_status", "").lower() != "measured"
                or "TIMEOUT" in row.get("note", "").upper()
                or "FALLBACK-SKIP" in row.get("note", "").upper()
                or any("timeout" in row.get(key, "").lower()
                       for key in ("duckdb_status", "outeryan_status"))
                or off is None or on is None or off <= 0 or on <= 0):
            continue
        ratio = off / on
        if not math.isfinite(ratio) or not 0 < ratio < threshold:
            continue
        family = FAMILIES.get(row.get("family", "").lower())
        if family is None:
            raise ValueError("Unknown family in eligible row: " + str(row.get("family")))
        if families and family not in families:
            continue
        relative = Path(row.get("sql_path", ""))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != family:
            raise ValueError("Unsafe/mismatched SQL path: " + str(relative))
        if str(relative) not in manifest:
            raise ValueError("Query is not in current active manifest: " + str(relative))
        if str(relative) in seen:
            raise ValueError("Duplicate measured query; select one run: " + str(relative))
        seen.add(str(relative))
        sql_path = (corpus / relative).resolve()
        if corpus.resolve() not in sql_path.parents:
            raise ValueError("SQL symlink escapes corpus: " + str(relative))
        actual_hash = digest(sql_path)
        if not row.get("sql_content_sha256") or actual_hash != row["sql_content_sha256"]:
            raise ValueError("Measured SQL differs from current SQL: " + str(relative))
        if manifest[str(relative)].get("content_sha256") != actual_hash:
            raise ValueError("SQL differs from current manifest: " + str(relative))
        cohort.append({"query": row["query"], "family": family, "sql_path": str(relative),
                       "sql_sha256": actual_hash, "source_off_s": off, "source_on_s": on,
                       "source_speedup": ratio, "source_added_wall_s": on - off,
                       "source_run": row.get("source_run", row.get("experiment_group")),
                       "source_host": row.get("execution_host"),
                       "source_database_signature": row.get("database_signature"),
                       "source_correctness": correct})
    cohort.sort(key=lambda row: (-row["source_added_wall_s"], row["sql_path"]))
    return cohort if limit is None else cohort[:limit]


def query_text(path):
    sql = Path(path).read_text(encoding="utf-8").strip()
    tokens = [token for token in SQL_TOKEN.findall(sql) if not token.startswith(("--", "/*"))]
    if not tokens or tokens[0].upper() != "SELECT" or any(token == ";" for token in tokens[:-1]):
        raise ValueError("Expected one bare SELECT: " + str(path))
    return sql if tokens[-1] == ";" else sql + "\n;"


def parse_trace(text):
    records = [dict(token.split("=", 1) for token in line.split()[1:] if "=" in token)
               for line in text.splitlines() if line.startswith("[OY_DECISION] ")]
    stages = re.findall(r"(?ms)^==== partial reduction ====\s*\n(.*?)(?=^====|^\[OY_DECISION\]|\Z)", text)
    fields = records[0] if len(records) == 1 else {}
    def counts(prefix):
        result = {}
        for name in COUNTS:
            value = fields.get(prefix + name)
            result[name] = int(value) if value is not None and value.isdigit() else None
        return result
    scheduled = counts("executed_")
    return {"decision_count": len(records), "decision_fields": fields,
            "selected_plan": fields.get("selected_plan"), "reason": fields.get("reason"),
            "scheduled_counts": scheduled,
            "scheduled_counts_available": all(value is not None for value in scheduled.values()),
            "reference_cost_counts": counts(""),
            "partial_reduction_stages": [stage.strip() for stage in stages],
            "trace_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def run_process(binary, database, sql, timeout, trace=None, environ=None):
    env = dict(os.environ if environ is None else environ)
    for key in UNSAFE_ENV:
        env.pop(key, None)
    if trace is not None:
        env["DUCKDB_OYTRACE"] = str(trace)
    try:
        process = subprocess.run([str(binary), "-readonly", "-no-init", "-batch", "-bail", str(database)],
                                 input=sql, text=True, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return {"status": "timeout", "error": "subprocess watchdog expired", "stdout": output}
    status = "ok"
    if process.returncode or "Error:" in process.stderr:
        status = "timeout" if re.search(r"maximum execution time|timeout|interrupt", process.stderr, re.I) else "error"
    return {"status": status, "returncode": process.returncode,
            "stdout": process.stdout, "stderr": process.stderr}


def settings(enabled, threads, timeout):
    # CALL and SET VARIABLE may themselves invoke the optimizer. Keep setup
    # outside OuterYan so the private trace contains only the target query.
    return ("SET disabled_optimizers='outer_yan';\nCALL disable_profiling();\n"
            + f"SET threads={threads};\nSET max_execution_time={timeout * 1000};\n"
            + f"SET VARIABLE outer_yan_partial_reduction = {'true' if enabled else 'false'};\n"
            + "SET disabled_optimizers='';\n")


def diagnose_mode(binary, database, sql, enabled, threads, timeout, trace, execute=False):
    setup = settings(enabled, threads, timeout)
    explained = run_process(binary, database, setup + "EXPLAIN " + sql + "\n", timeout + 5, trace)
    trace_info = parse_trace(trace.read_text(encoding="utf-8") if trace.exists() else "")
    explained.update(trace_info)
    explained["plan"] = explained.pop("stdout")
    if explained["status"] == "ok" and trace_info["decision_count"] != 1:
        explained.update(status="error", error="expected exactly one OuterYan decision record")
    counter_fields_present = all("executed_" + name in trace_info["decision_fields"] for name in COUNTS)
    if explained["status"] == "ok" and (not counter_fields_present or
            (trace_info["selected_plan"] == "OUTERYAN" and not trace_info["scheduled_counts_available"])):
        explained.update(status="error", error="scheduled counters unavailable; rebuild with partial-reduction trace support")
    fields = trace_info["decision_fields"]
    if explained["status"] == "ok" and (fields.get("selection_mode") != "GATED" or
            (trace_info["selected_plan"] == "OUTERYAN" and fields.get("cost_gate_applied") != "1")):
        explained.update(status="error", error="trace does not confirm normally gated plan selection")
    output = {"partial_reduction": enabled, "explain": explained}
    if not execute:
        return output
    if explained["status"] != "ok":
        output["timing"] = {"status": "not-run", "reason": "EXPLAIN/trace failed"}
        return output
    # Traces belong to EXPLAIN only. Timed execution emits no rows and remains a
    # bare SELECT; wrappers or LIMIT could change the chosen plan.
    script = (".mode trash\n.timer off\n" + setup + sql + "\n.print OY_WARMUP_DONE\n"
              + ".timer on\n" + sql + "\n.timer off\n")
    timing = run_process(binary, database, script, timeout * 2 + 5)
    samples = [float(value) for value in TIMER.findall(timing.pop("stdout"))]
    timing.update(warmup_runs=1, measured_runs=1, correctness="NOT-CHECKED",
                  protocol="one bare warm-up then one bare unprofiled timed SELECT; tracing disabled",
                  sample_s=None)
    if timing["status"] == "ok":
        if len(samples) != 1 or not math.isfinite(samples[0]) or samples[0] < 0:
            timing.update(status="error", error="expected exactly one finite nonnegative timer sample")
        else:
            timing["sample_s"] = samples[0]
    output["timing"] = timing
    return output


def database_metadata(path, family):
    path = path.resolve()
    if not path.is_file():
        raise ValueError("Database file does not exist; build separately or set an explicit path: " + str(path))
    stat = path.stat()
    signature = hashlib.sha256(json.dumps([str(path), stat.st_size, stat.st_mtime_ns],
                                          separators=(",", ":")).encode()).hexdigest()
    return {"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "signature": signature, "actual_scale": "unverified by this runner",
            "configured_scale_parameter": os.environ.get(family.upper() + "_SF", "50")
            if family in ("tpch", "tpcds") else None,
            "path_override": bool(os.environ.get(family.upper() + "_DB"))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--family", choices=("graph", "tpch", "tpcds", "job"), action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=30, help="seconds per statement; each mode is independent")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True, help="new JSON report (existing files are not overwritten)")
    parser.add_argument("--execute", action="store_true", help="also warm and time each mode; NOT an equivalence test")
    parser.add_argument("--label", default="", help="user-supplied experiment/scale label, not scale verification")
    parser.add_argument("--duckdb", type=Path, default=Path(os.environ.get("DUCKDB_BIN", ROOT / "build/release/duckdb")))
    args = parser.parse_args(argv)
    if not 0 < args.threshold <= 1 or args.timeout <= 0 or args.threads <= 0 or (args.limit is not None and args.limit <= 0):
        parser.error("require 0 < threshold <= 1, positive timeout/threads/limit")
    if args.out.exists() or args.out.suffix.lower() != ".json":
        parser.error("--out must be a new .json path; original results are never overwritten")
    binary = args.duckdb.resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        parser.error("DuckDB binary is not executable; build separately: " + str(binary))
    manifest_hash = digest(CORPUS / "manifest.csv")
    cohort = load_cohort(args.csv, args.threshold, args.family, args.limit, corpus=CORPUS)
    binary_hash, csv_hash = digest(binary), digest(args.csv)
    databases = {family: database_metadata(database_path(family, ROOT), family)
                 for family in sorted({row["family"] for row in cohort})}
    rows = []
    with tempfile.TemporaryDirectory(prefix="outeryan-partial-reduction-") as scratch:
        for index, source in enumerate(cohort):
            database = Path(databases[source["family"]]["path"])
            sql = query_text(CORPUS / source["sql_path"])
            result = dict(source, modes={})
            for enabled in (False, True):
                key = "enabled" if enabled else "disabled"
                trace = Path(scratch) / f"{index}_{key}.trace"
                result["modes"][key] = diagnose_mode(binary, database, sql, enabled, args.threads,
                                                    args.timeout, trace, args.execute)
            off, on = (result["modes"][key].get("timing", {}).get("sample_s") for key in ("disabled", "enabled"))
            result["partial_reduction_speedup"] = off / on if off is not None and on is not None and on > 0 else None
            rows.append(result)
            print(f"[{index + 1}/{len(cohort)}] {source['query']} "
                  + "; ".join(key + "=" + mode["explain"]["status"] for key, mode in result["modes"].items()), flush=True)
    unchanged = (binary_hash == digest(binary) and csv_hash == digest(args.csv)
                 and manifest_hash == digest(CORPUS / "manifest.csv")
                 and all(row["sql_sha256"] == digest(CORPUS / row["sql_path"]) for row in cohort)
                 and all(value["signature"] == database_metadata(Path(value["path"]), family)["signature"]
                         for family, value in databases.items()))
    failures = sum(mode["explain"]["status"] != "ok" or
                   (args.execute and mode.get("timing", {}).get("status") != "ok")
                   for row in rows for mode in row["modes"].values())
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "host": socket.gethostname(),
              "label": args.label, "label_is_user_supplied": True, "execute": args.execute,
              "correctness": "NOT-CHECKED: run the normal correctness harness before accepting rewritten plans",
              "source_csv": str(args.csv.resolve()), "source_csv_sha256": csv_hash,
              "manifest_sha256": manifest_hash, "duckdb_binary": str(binary),
              "duckdb_sha256": binary_hash, "threads": args.threads, "statement_timeout_s": args.timeout,
              "threshold_exclusive": args.threshold, "order": "descending original added wall time",
              "comparison_definition": "partial_reduction_speedup = newly timed disabled/ enabled; not DuckDB/OuterYan and not the source-machine timings",
              "family_counts": dict(Counter(row["family"] for row in rows)), "queries": len(rows),
              "normal_cost_gate": True, "removed_environment_overrides": list(UNSAFE_ENV),
              "counter_definition": "scheduled_counts are post-lowering executed_round* counts; reference_cost_counts are pre-partial cost-model counts",
              "databases": databases, "inputs_unchanged": unchanged, "failed_modes": failures, "rows": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(f"Wrote {args.out}; failed modes={failures}; inputs unchanged={unchanged}")
    return 1 if failures or not unchanged else 0


if __name__ == "__main__":
    raise SystemExit(main())
