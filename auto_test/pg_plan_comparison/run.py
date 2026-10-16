#!/usr/bin/env python3
"""Capture, validate, and measure two PostgreSQL/OuterYan plan-space cases.

Reuse original JOB/TPC-H databases. Linux provisioning is in server.sh.
Only Python's standard library is required; Graphviz is optional.
"""

import argparse
import csv
import filecmp
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from datasets import assert_unchanged, export_tables, import_tables, source_database
from plans import (accepted_pair, decision, explain_tree, grouping, nodes, pg_tree,
                   profile_metrics, query_text, replay_verified, semantic,
                   sha256, trace_evidence, validate_tree)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MODES = ("PG-Replay", "DuckDB", "OuterYan")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def write_summary(out, rows):
    with (out / "summary.csv").open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def replay_diagnostics(path):
    if shutil.which("grep"):
        result = subprocess.run(["grep", "-a", r"^\[PGPLAN\] ", str(path.resolve())],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode not in (0, 1):
            raise RuntimeError("reading replay diagnostics failed: " + result.stderr)
        return result.stdout
    with path.open() as source:
        return "".join(line for line in source if line.startswith("[PGPLAN] "))


def command(argv, sql=None, stdout=None, stderr=None, env=None, timeout=120):
    """Use argv, never a shell; preserve failure artifacts and reject partial runs."""
    with tempfile.TemporaryFile(mode="w+") as errors:
        err = stderr if stderr is not None else errors
        result = subprocess.run([str(a) for a in argv], input=sql, text=True,
                                stdout=stdout or subprocess.PIPE, stderr=err,
                                timeout=timeout, env=env)
        if result.returncode:
            if stderr is None:
                errors.seek(0)
                detail = errors.read()[-2500:]
            else:
                detail = "see " + str(stderr.name)
            raise RuntimeError(f"{Path(argv[0]).name} exited {result.returncode}: {detail}")
        return result.stdout or ""


def duck_env(trace=None):
    env = os.environ.copy()
    # Keep every measurement free of diagnostic output and diagnostic overrides.
    for key in list(env):
        if key.startswith("DUCKDB_OY") or key.startswith("DUCKDB_SJ"):
            del env[key]
    if trace:
        env["DUCKDB_OYTRACE"] = str(trace)
    return env


class DuckDB:
    def __init__(self, args):
        self.args = args

    def run(self, db, sql, log, output=None, readonly=True, trace=None, timeout=None):
        argv = [self.args.duckdb, db, "-init", os.devnull, "-batch", "-bail"]
        if readonly:
            argv.append("-readonly")
        with log.open("w") as stderr:
            if output:
                with output.open("w") as stdout:
                    command(argv, sql, stdout, stderr, duck_env(trace), timeout or self.args.timeout)
                return ""
            return command(argv, sql, stderr=stderr, env=duck_env(trace),
                           timeout=timeout or self.args.timeout)

    def setup(self, mode, artifact):
        sql = f".timer off\nSET threads={self.args.threads};\nSET memory_limit={literal(self.args.memory_limit)};\n"
        sql += f"SET max_execution_time={self.args.timeout * 1000};\n"
        sql += "RESET VARIABLE pgplan;\nRESET VARIABLE outer_yan_pg_replay_plan;\n"
        sql += "SET disabled_optimizers TO " + ("''" if mode == "OuterYan" else "'outer_yan'") + ";\n"
        if mode == "PG-Replay":
            sql += "SET VARIABLE pgplan=" + literal(artifact) + ";\n"
        return sql


class Postgres:
    """Own a disposable cluster. Never start, stop, or modify an existing server."""

    def __init__(self, args, out):
        self.args, self.out = args, out
        self.bin = args.pg_bin_dir
        self.data = out / "pgdata"
        self.socket = None

    def __enter__(self):
        self.socket = tempfile.TemporaryDirectory(prefix="oypg-")
        env = os.environ.copy()
        env["PG_OJ_TRACE"] = "1"
        try:
            with (self.out / "initdb.log").open("w") as log:
                command([self.bin / "initdb", "-D", self.data, "-A", "trust", "-U", "oy_study",
                         "--no-locale", "-E", "UTF8"], stdout=log, env=env)
            # A short, private Unix-socket directory avoids socket path limits;
            # TCP is disabled. No existing server or port is used.
            command([self.bin / "pg_ctl", "-D", self.data, "-l", self.out / "postgres.log",
                     "-o", f"-h '' -k {self.socket.name} -p 55439 -c autovacuum=off", "-w", "start"], env=env)
        except BaseException:
            self.close()
            raise
        return self

    def close(self):
        # A second Ctrl+C must not interrupt pg_ctl and leave the cluster running.
        previous = {sig: signal.signal(sig, signal.SIG_IGN)
                    for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            if (self.data / "postmaster.pid").exists():
                command([self.bin / "pg_ctl", "-D", self.data, "-m", "fast", "-w", "stop"])
            if self.socket:
                self.socket.cleanup()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    def __exit__(self, *unused):
        self.close()

    def run(self, sql, log, output=None, csv_output=False, timeout=None):
        argv = [self.bin / "psql", "-X", "-w", "-h", self.socket.name, "-p", "55439",
                "-U", "oy_study", "-d", "postgres", "-qAt", "-v", "ON_ERROR_STOP=1"]
        if csv_output:
            argv = [self.bin / "pg_bare_query", self.socket.name, "55439", "oy_study", "postgres", "4"]
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("PG"):
                del env[key]
        with log.open("w") as stderr:
            if output:
                with output.open("w") as stdout:
                    command(argv, sql, stdout, stderr, env, timeout or self.args.timeout)
                return ""
            return command(argv, sql, stderr=stderr, env=env, timeout=timeout or self.args.timeout)

    def setup(self, family, loading=False):
        return (f"SET search_path=pgplan_{family},pg_catalog;\n"
                "SET max_parallel_workers_per_gather=0;\n"
                f"SET statement_timeout={(self.args.load_timeout if loading else self.args.timeout) * 1000};\n")


def prepare_case(args, duck, case, spec, directory):
    sql = query_text(HERE / spec["query"])
    (directory / "query.sql").write_text(sql + ";\n")
    db = source_database(args, duck, spec, args.out)
    data = export_tables(args, duck, spec, directory, db)
    data.update(query_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                source_query=spec["source"], source_query_sha256=sha256(ROOT / spec["source"]))
    write_json(directory / "data.json", data)
    return sql, db, data


def capture(args, duck, pg, directory, case, spec, sql, db, data):
    import_tables(pg, spec, directory, data)
    schema = "pgplan_" + spec["family"]
    settings = json.loads(pg.run(pg.setup(spec["family"]) + """SELECT json_build_object(
'version_num',current_setting('server_version_num'),
'version',version(), 'geqo',current_setting('geqo'),
'geqo_threshold',current_setting('geqo_threshold'),
'join_collapse_limit',current_setting('join_collapse_limit'),
'from_collapse_limit',current_setting('from_collapse_limit'),
'max_parallel_workers_per_gather',current_setting('max_parallel_workers_per_gather'),
'search_path',current_setting('search_path'));
""", directory / "pg_settings.log"))
    if int(settings["version_num"]) != 160002:
        raise ValueError("C++ replay requires PostgreSQL 16.2 (160002)")
    if min(int(settings[k]) for k in ("geqo_threshold", "join_collapse_limit", "from_collapse_limit")) <= 3:
        raise ValueError("unexpected PG enumeration settings for a three-table query")
    write_json(directory / "pg_settings.json", settings)
    capture_sql = pg.setup(spec["family"]) + "EXPLAIN (VERBOSE, FORMAT JSON, SETTINGS) " + sql + ";\n"
    (directory / "capture_pg.sql").write_text(capture_sql)
    pg.run(capture_sql, directory / "pg_trace.log", directory / "pg_explain.json")
    explained = json.loads((directory / "pg_explain.json").read_text())
    if len(explained) != 1:
        raise ValueError("expected one PostgreSQL plan")
    expected_settings = {"max_parallel_workers_per_gather": "0", "search_path": schema + ", pg_catalog"}
    if explained[0].get("Settings") != expected_settings:
        raise ValueError("unexpected PG planner overrides: " + str(explained[0].get("Settings")))
    pgplan = pg_tree(explained[0]["Plan"], schema, spec["aliases"])
    validate_tree(pgplan, spec["tables"])
    artifact = directory / "pg_replay.json"
    write_json(artifact, {"format": "duckyan.pg_join_tree.v1", "query_sha256": data["query_sha256"],
                         "query_sha256_canonicalization": "duckyan.sql_text.v1",
                         "postgres": {"version_num": 160002, "settings": expected_settings,
                                      "plan_schema": schema,
                                      "plan_data": spec["family"] + "-duckdb-full"},
                         "data_provenance": data, "tree": pgplan})
    trees = {}
    for mode in MODES:
        trace = directory / "outeryan.trace" if mode == "OuterYan" else None
        # Replay's SQL hash verifier accepts plain EXPLAIN only. Its final
        # semantic-signature check proves the logical tree survived; the later
        # bare-query profile also verifies the physical join tree.
        explain = "EXPLAIN " if mode == "PG-Replay" else "EXPLAIN (FORMAT JSON) "
        text = duck.run(db, duck.setup(mode, artifact) + explain + sql + ";\n",
                        directory / (mode + ".explain.log"), trace=trace)
        (directory / (mode + ".explain.txt")).write_text(text)
        trees[mode] = pgplan if mode == "PG-Replay" else explain_tree(text, spec["tables"])
        if mode == "PG-Replay":
            replay_verified(text + (directory / (mode + ".explain.log")).read_text(), 1)
    selected = decision((directory / "outeryan.trace").read_text())
    different = grouping(pgplan) != grouping(trees["OuterYan"])
    has_full = any(n.get("join_type") == "full" for n in nodes(pgplan))
    evidence = trace_evidence((directory / "pg_trace.log").read_text(), trees["OuterYan"], case, spec["pg_base_relids"])
    reasons = []
    if selected.get("selected_plan") != "OUTERYAN" or selected.get("cost_gate_applied") != "1":
        reasons.append("OuterYan was not selected by the normal cost gate")
    if not different:
        reasons.append("PostgreSQL and OuterYan have the same grouping")
    if (case == "B") != has_full:
        reasons.append("PostgreSQL FULL-join survival does not match the case")
    if case == "A" and re.search(r"\bFULL\b", sql, re.I):
        reasons.append("Case A contains FULL in its input SQL")
    if evidence["status"] == "unproven":
        reasons.append("no instrumented proof of the additional grouping; use the patched PostgreSQL build")
    controls = []
    for relative in spec["controls"]:
        control_sql = query_text(HERE / relative)
        name = Path(relative).stem
        text = pg.run(pg.setup(spec["family"]) + "EXPLAIN (VERBOSE, FORMAT JSON) " + control_sql + ";\n",
                      directory / (name + ".trace.log"))
        (directory / (name + ".plan.json")).write_text(text)
        (directory / (name + ".sql")).write_text(control_sql + ";\n")
        # These controls keep the same three base RTE positions as A.
        log = (directory / (name + ".trace.log")).read_text()
        accepted = accepted_pair(log, spec["pg_base_relids"], {"title", "movie_info"})
        controls.append({"query": relative, "title_info_pair_accepted": accepted})
        if not accepted:
            reasons.append("PG positive enumeration control failed: " + name)
    selection = {"case": case, "family": spec["family"], "eligible": not reasons, "reasons": reasons,
                 "controls": controls,
                 "pg_full_survives": has_full, "pg_vs_oy_grouping_differs": different,
                 "groupings": {m: grouping(t) for m, t in trees.items()},
                 "outeryan_decision": selected, "evidence": evidence, "trees": trees,
                 "selection_rule": "fixed benchmark-derived structural cases; no timing used for inclusion"}
    write_json(directory / "selection.json", selection)
    return artifact, selection


def result_validator():
    validators = []
    if all(shutil.which(name) for name in ("grep", "wc", "tr")):
        validators.append("grep/wc/tr integer CSV fast path")
    validators.append("awk" if shutil.which("awk") else "python")
    return "; fallback: ".join(validators)


def clean_and_sort(path, timeout, columns=4):
    """Exact multiset comparison of integer/NULL fields, using disk sorting."""
    clean = path.with_suffix(".rows.csv")
    rows = 0
    canonical = False
    if all(shutil.which(name) for name in ("grep", "wc", "tr")):
        pattern = r"^(NULL|-?[0-9]+)(,(NULL|-?[0-9]+)){" + str(columns - 1) + "}\r*$"
        checked = subprocess.run(["grep", "-a", "-q", "-E", "-v", pattern, str(path.resolve())],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                 env={**os.environ, "LC_ALL": "C"}, timeout=timeout)
        if checked.returncode not in (0, 1):
            raise ValueError("result format check failed: " + checked.stderr.decode(errors="replace"))
        canonical = checked.returncode == 1
    if canonical:
        # Validate every field before normalizing CSV line endings. Removing CR
        # is safe only after the whole-row pattern excludes it inside fields.
        clean = path
        rows = int(command(["wc", "-l", path], timeout=timeout).split()[0])
        if path.stat().st_size:
            with path.open("rb") as source:
                source.seek(-1, os.SEEK_END)
                rows += source.read(1) != b"\n"
        cr = subprocess.run(["grep", "-a", "-q", "\r", str(path.resolve())],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            env={**os.environ, "LC_ALL": "C"}, timeout=timeout)
        if cr.returncode not in (0, 1):
            raise ValueError("CSV line-ending check failed: " + cr.stderr.decode(errors="replace"))
        if cr.returncode == 0:
            clean = path.with_suffix(".rows.csv")
            with path.open("rb") as source, clean.open("wb") as output:
                subprocess.run(["tr", "-d", "\r"], stdin=source, stdout=output,
                               env={**os.environ, "LC_ALL": "C"}, timeout=timeout, check=True)
    elif shutil.which("awk"):
        # Keep the exact check, but avoid billions of Python regex calls on SF100.
        # Filenames travel through the environment, never through awk source text.
        diagnostics = path.with_suffix(".diagnostics.jsonl")
        clean.write_text("")
        diagnostics.write_text("")
        program = r'''
BEGIN { FS=","; output=ENVIRON["PGPLAN_CLEAN"]; diagnostics=ENVIRON["PGPLAN_DIAGNOSTICS"]; columns=ENVIRON["PGPLAN_COLUMNS"]+0 }
/^\[PGPLAN\] / { print substr($0,10) > diagnostics; next }
{
    sub(/\r+$/, "")
    if (NF != columns) { bad=1; exit 1 }
    for (i=1; i<=NF; i++) if ($i != "NULL" && $i !~ /^-?[0-9]+$/) { bad=1; exit 1 }
    print $0 > output
    rows++
}
END { if (!bad) printf "%.0f\n", rows }
'''
        env = {**os.environ, "LC_ALL": "C", "PGPLAN_CLEAN": str(clean.resolve()),
               "PGPLAN_DIAGNOSTICS": str(diagnostics.resolve()), "PGPLAN_COLUMNS": str(columns)}
        result = subprocess.run(["awk", program, str(path.resolve())], env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if result.returncode:
            raise ValueError("malformed result row or failed result check in " + str(path) + ": " + result.stderr)
        rows = int(result.stdout.strip())
        with diagnostics.open() as source:
            for line in source:
                json.loads(line)
        diagnostics.unlink()
    else:
        with path.open() as src, clean.open("w") as dst:
            for line in src:
                if line.startswith("[PGPLAN] "):
                    json.loads(line[len("[PGPLAN] "):])
                    continue
                values = line.rstrip("\r\n").split(",")
                if len(values) != columns or any(v != "NULL" and not re.fullmatch(r"-?[0-9]+", v) for v in values):
                    raise ValueError("malformed result row in " + str(path))
                dst.write(",".join(values) + "\n")
                rows += 1
    sorted_path = path.with_suffix(".sorted.csv")
    with sorted_path.open("w") as output:
        command(["sort", clean], stdout=output, env={**os.environ, "LC_ALL": "C"}, timeout=timeout)
    if clean != path:
        clean.unlink()
    return sorted_path, rows


def correctness(args, duck, pg, directory, spec, sql, db, artifact, data):
    assert_unchanged(data)
    outputs, counts = {}, {}
    for mode in MODES:
        raw = directory / (mode + ".result.csv")
        log = directory / (mode + ".result.log")
        prefix = ".mode csv\n.headers off\n.nullvalue NULL\n"
        duck.run(db, duck.setup(mode, artifact) + prefix + sql + ";\n", log, raw)
        if mode == "PG-Replay":
            replay_verified(replay_diagnostics(raw) + log.read_text(), 1)
        outputs[mode], counts[mode] = clean_and_sort(raw, args.timeout, spec["result_columns"])
    pg_raw = directory / "PostgreSQL.result.csv"
    pg.run(pg.setup(spec["family"]) + sql + ";\n", directory / "PostgreSQL.result.log", pg_raw, csv_output=True)
    outputs["PostgreSQL"], counts["PostgreSQL"] = clean_and_sort(pg_raw, args.timeout, spec["result_columns"])
    baseline = outputs["DuckDB"]
    if any(not filecmp.cmp(baseline, path, shallow=False) for path in outputs.values()):
        raise ValueError("bare-query multiset mismatch; result files retained")
    result = {"status": "exact_multiset_equal", "row_counts": counts,
              "sorted_csv_sha256": sha256(baseline), "null_marker": "NULL",
              "method": "bare SELECT; external byte sort; exact comparison with multiplicity"}
    write_json(directory / "correctness.json", result)
    if not args.keep_results:
        for path in outputs.values():
            path.unlink()
        for mode in (*MODES, "PostgreSQL"):
            (directory / (mode + ".result.csv")).unlink()
    return result


def measure(args, duck, directory, case, spec, sql, db, artifact, selection, correct):
    metrics = {}
    # Profiles are separate executions, following a warm-up. They never supply
    # the runtime column. Read the immediate data children of real joins only.
    for mode in MODES:
        path = directory / (mode + ".profile.json")
        script = (".mode trash\nCALL disable_profiling();\n" + duck.setup(mode, artifact) + sql + ";\n"
                  "RESET VARIABLE pgplan;\nPRAGMA enable_profiling='json';\n"
                  + "PRAGMA profiling_output=" + literal(path) + ";\n"
                  + duck.setup(mode, artifact) + sql + ";\n")
        text = duck.run(db, script, directory / (mode + ".profile.log"), timeout=2 * args.timeout + 30)
        if mode == "PG-Replay":
            replay_verified(text + (directory / (mode + ".profile.log")).read_text(), 2)
        tree, metrics[mode] = profile_metrics(json.loads(path.read_text()), sql, spec["tables"])
        if semantic(tree) != semantic(selection["trees"][mode]):
            raise ValueError("profiled plan changed after screening")
        if metrics[mode]["result_rows"] != correct["row_counts"][mode]:
            raise ValueError("profile result cardinality disagrees with correctness run")
        metrics[mode]["tree"] = tree
    # One connection, one untimed warm-up per mode, seeded interleaving. The
    # timer surrounds only the unwrapped query, including planning and drain.
    script = ".mode trash\nCALL disable_profiling();\n"
    for mode in MODES:
        script += duck.setup(mode, artifact) + sql + ";\n"
    order = []
    rng = random.Random(args.seed + ord(case))
    for repetition in range(args.runs):
        modes = list(MODES)
        rng.shuffle(modes)
        for mode in modes:
            order.append({"mode": mode, "repetition": repetition + 1})
            script += duck.setup(mode, artifact) + ".timer on\n" + sql + ";\n.timer off\n"
    (directory / "timing.sql").write_text(script)
    text = duck.run(db, script, directory / "timing.log", timeout=(len(order) + 3) * args.timeout + 30)
    (directory / "timing.stdout").write_text(text)
    replay_verified(text + (directory / "timing.log").read_text(), args.runs + 1)
    samples = re.findall(r"Run Time \(s\): real ([0-9]+(?:\.[0-9]+)?)", text)
    if len(samples) != len(order):
        raise ValueError(f"expected {len(order)} complete timing samples; got {len(samples)}")
    for entry, sample in zip(order, samples):
        entry["runtime_ms"] = float(sample) * 1000
    write_json(directory / "timing_samples.json", order)
    rows = []
    for mode in MODES:
        times = [e["runtime_ms"] for e in order if e["mode"] == mode]
        row = {"case": case, "plan": mode, "runtime_median_ms": statistics.median(times),
               "runtime_min_ms": min(times), "runtime_max_ms": max(times), "runs": len(times),
               "threads": args.threads, **{k: v for k, v in metrics[mode].items() if k != "tree"},
               "grouping": selection["groupings"][mode], "evidence": selection["evidence"]["status"]}
        rows.append(row)
    write_json(directory / "metrics.json", metrics)
    return rows, metrics


def figure(out, cases, all_metrics):
    lines = ["digraph plans {", 'graph [fontname="Helvetica", compound=true];',
             'node [shape=box, fontname="Helvetica"];', 'edge [dir=none];']
    index = 0
    panels = []
    for case, mode in (("A", "PG-Replay"), ("A", "OuterYan"), ("B", "PG-Replay"), ("B", "OuterYan")):
        if case not in all_metrics:
            continue
        rows = next(r for r in cases if r["case"] == case and r["plan"] == mode)
        start = len(lines)
        lines += [f"subgraph cluster_{case}_{mode.replace('-', '_')} {{",
                  'label=' + json.dumps(f"Case {case}: {mode}\n{rows['runtime_median_ms']:.3f} ms | "
                                       f"join input {rows['real_join_input_rows']:,}\n"
                                       f"max intermediate {rows['max_intermediate_rows']:,}") + ";"]

        def visit(tree):
            nonlocal index
            index += 1
            name = "n" + str(index)
            if tree["op"] == "scan":
                label = tree["relation"].upper()
            else:
                label = tree["join_type"].upper() + "\nrows=" + str(tree["output_rows"])
            lines.append(name + " [label=" + json.dumps(label) + "];")
            if tree["op"] == "join":
                for child, side in ((tree["left"], "L"), (tree["right"], "R")):
                    child_name = visit(child)
                    lines.append(f'{name} -> {child_name} [label="{side}"];')
            return name

        visit(all_metrics[case][mode]["tree"])
        lines.append("}")
        panels.append((f"{case}_{mode}", lines[start:]))
    lines.append("}")
    dot = out / "plans.dot"
    dot.write_text("\n".join(lines) + "\n")
    if shutil.which("dot"):
        # Compose individually laid-out trees as A(PG,OY) / B(PG,OY). DOT's
        # unconstrained packing otherwise tends to put all four in one row.
        rendered = []
        for name, panel in panels:
            source = out / (name + ".dot")
            source.write_text("\n".join(lines[:3] + panel + ["}"]) + "\n")
            root = ET.fromstring(command(["dot", "-Tsvg", source]))
            view = [float(x) for x in root.attrib["viewBox"].split()]
            for element in root.iter():
                if "id" in element.attrib:
                    element.attrib["id"] = name + "_" + element.attrib["id"]
            rendered.append((root, view[2], view[3]))
        ns = "http://www.w3.org/2000/svg"
        ET.register_namespace("", ns)
        width = max(w for _, w, _ in rendered)
        height = max(h for _, _, h in rendered)
        gap = 20
        cols, row_count = 2, (len(rendered) + 1) // 2
        total_w, total_h = cols * (width + gap) + gap, row_count * (height + gap) + gap
        canvas = ET.Element("{" + ns + "}svg", {"viewBox": f"0 0 {total_w} {total_h}",
                                                "width": str(total_w), "height": str(total_h)})
        ET.SubElement(canvas, "{" + ns + "}rect", {"width": "100%", "height": "100%", "fill": "white"})
        for i, (root, _, _) in enumerate(rendered):
            root.attrib.update(x=str(gap + (i % cols) * (width + gap)),
                               y=str(gap + (i // cols) * (height + gap)),
                               width=str(width), height=str(height))
            canvas.append(root)
        ET.ElementTree(canvas).write(out / "plans.svg", encoding="unicode", xml_declaration=True)


def report(out, selections, rows):
    lines = ["# PostgreSQL plan comparison", "",
             "These are fixed benchmark-derived mechanism witnesses, not a speedup-ranked corpus sample.", "",
             "Case A derives from JOB 3c; Case B derives from TPC-H Q3. Original tables are reused in full. "
             "These modified queries are not official benchmark scores.", "",
             "A validated additional grouping demonstrates a concrete PostgreSQL search-space gap. "
             "A lower runtime demonstrates a better plan for that case. Two witnesses do not prove "
             "global superset coverage or completeness; those require an equivalence/coverage argument.", "",
             "Timing: unprofiled bare SELECT, warm cache, includes planning and result drain. "
             "All three measured plans run in the same DuckDB binary on the same original database (opened read-only).", "",
             "| Case | Plan | Median ms | Real-join input | Max intermediate | Max nonroot intermediate |",
             "|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['case']} | {row['plan']} | {row['runtime_median_ms']:.3f} | "
                     f"{row['real_join_input_rows']:,} | {row['max_intermediate_rows']:,} | "
                     f"{row['max_nonroot_intermediate_rows']:,} |")
    for s in selections:
        lines += ["", f"## Case {s['case']}", "", f"Eligible: {s['eligible']}. " + "; ".join(s["reasons"]),
                  "", "PG grouping: `" + s["groupings"]["PG-Replay"] + "`",
                  "", "OuterYan grouping: `" + s["groupings"]["OuterYan"] + "`",
                  "", "Search-space evidence: **" + s["evidence"]["status"] + "**."]
        measured = {r["plan"]: r for r in rows if r["case"] == s["case"]}
        if measured:
            pg_ms, oy_ms = (measured[m]["runtime_median_ms"] for m in ("PG-Replay", "OuterYan"))
            lines += ["", f"PG-Replay / OuterYan runtime ratio: {pg_ms / oy_ms:.3f}x. "
                      + ("OuterYan is faster in this run." if oy_ms < pg_ms else "No runtime improvement in this run.")]
        if s["evidence"]["status"] == "unproven":
            lines += ["", "Do not claim PostgreSQL cannot enumerate this grouping. "
                      "The observed plans alone do not distinguish legality from costing."]
        else:
            lines += ["", "```text", *s["evidence"]["records"], "```"]
    lines += ["", "Max intermediate includes the final join output. In the FULL witness it can "
              "be equal even when the nonroot intermediate and join input shrink.", "",
              "Runtime includes reduction/SJ work. Real-join input excludes SJ operators; "
              "this experiment does not isolate reordering from reduction cost.", "",
              "Typed replay also bypasses native statistics propagation and join elimination. "
              "Same grouping does not imply identical filters, physical orientation, or execution work. "
              "Use the legality/barrier evidence alongside these measurements; runtime is not "
              "a pure grouping-only causal effect.", ""]
    (out / "report.md").write_text("\n".join(lines))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new output directory; never overwritten")
    parser.add_argument("--duckdb", type=Path, default=ROOT / "build/release/duckdb")
    parser.add_argument("--pg-bin-dir", type=Path, default=ROOT / "postgres/postgresql/bin")
    parser.add_argument("--job-db", type=Path, default=ROOT / "job_db")
    parser.add_argument("--tpch-db", type=Path, default=ROOT / "tpch_db")
    parser.add_argument("--job-parquet-dir", type=Path, default=ROOT / "job_data")
    parser.add_argument("--download-missing-job", action="store_true",
                        help="if no JOB DB/cache exists, download only the three required original tables")
    parser.add_argument("--case", choices=("A", "B", "both"), default="both")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260929)
    parser.add_argument("--timeout", type=int, default=600, help="per statement/process seconds")
    parser.add_argument("--load-timeout", type=int, default=1800, help="data import/export seconds")
    parser.add_argument("--memory-limit", default="4GB")
    parser.add_argument("--plans-only", action="store_true", help="screen plans/evidence; do not execute or time queries")
    parser.add_argument("--keep-results", action="store_true", help="keep equal result multisets as well as failed ones")
    args = parser.parse_args()
    if min(args.threads, args.runs, args.timeout, args.load_timeout) < 1:
        parser.error("counts/timeouts must be positive")
    if args.runs % 2 != 1:
        parser.error("runs must be odd")
    for key in ("out", "duckdb", "pg_bin_dir", "job_db", "tpch_db", "job_parquet_dir"):
        setattr(args, key, getattr(args, key).resolve())
    if any(c in str(args.out) for c in "'\n\r\\"):
        parser.error("output path cannot contain apostrophes, backslashes, or newlines (psql copy path)")
    for binary in (args.duckdb, *(args.pg_bin_dir / b for b in ("initdb", "pg_ctl", "psql", "postgres", "pg_bare_query"))):
        if not binary.is_file() or not os.access(binary, os.X_OK):
            parser.error("missing executable: " + str(binary))
    if not shutil.which("sort"):
        parser.error("external sort is required")
    if os.environ.get("DUCKDB_OY_FORCE_CANDIDATE") not in (None, "", "0"):
        parser.error("unset DUCKDB_OY_FORCE_CANDIDATE; this experiment requires normal selection")
    return args


def main():
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    duck = DuckDB(args)
    specs = json.loads((HERE / "cases.json").read_text())
    settings = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    settings.update(platform=platform.platform(), cpu_count=os.cpu_count(),
                    pg_autovacuum=False, pg_statistics_policy="explicit ANALYZE after import",
                    pg_result_transport="libpq single-row mode; unchanged bare SELECT",
                    pg_stream_binary_sha256=sha256(args.pg_bin_dir / "pg_bare_query"),
                    result_validator=result_validator(),
                    started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    duckdb_binary_sha256=sha256(args.duckdb),
                    postgres_binary_sha256=sha256(args.pg_bin_dir / "postgres"),
                    cases_manifest_sha256=sha256(HERE / "cases.json"),
                    pg_patch_sha256=sha256(HERE / "patches/postgresql-16.2-ojtrace.patch"),
                    source_knobs_sha256=sha256(ROOT / "src/include/duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp"))
    write_json(args.out / "environment.json", settings)
    selections, rows, metrics = [], [], {}
    try:
        with Postgres(args, args.out) as pg:
            for case in ("A", "B") if args.case == "both" else (args.case,):
                directory = args.out / ("case_" + case.lower())
                directory.mkdir()
                print(f"Case {case}: prepare shared data; capture and screen plans", flush=True)
                spec = specs[case]
                sql, db, data = prepare_case(args, duck, case, spec, directory)
                artifact, selection = capture(args, duck, pg, directory, case, spec, sql, db, data)
                selections.append(selection)
                report(args.out, selections, rows)
                if not selection["eligible"]:
                    print(f"Case {case}: ineligible: {'; '.join(selection['reasons'])}", flush=True)
                    continue
                if args.plans_only:
                    continue
                print(f"Case {case}: compare four bare-query multisets; then profile and time", flush=True)
                correct = correctness(args, duck, pg, directory, spec, sql, db, artifact, data)
                result, metrics[case] = measure(args, duck, directory, case, spec, sql, db, artifact, selection, correct)
                assert_unchanged(data)
                rows.extend(result)
                # Preserve completed cases if a later import/query is interrupted.
                write_json(directory / "measurements.json", result)
                write_summary(args.out, rows)
                report(args.out, selections, rows)
        if rows:
            figure(args.out, rows, metrics)
        report(args.out, selections, rows)
        eligible = all(s["eligible"] for s in selections)
        status = ("screened" if args.plans_only else "complete") if eligible else "ineligible"
        write_json(args.out / "status.json", {"status": status,
                                             "all_cases_eligible": eligible, "measured_rows": len(rows)})
        print(args.out / "report.md", flush=True)
        return 0 if eligible else 2
    except BaseException as exc:
        write_json(args.out / "status.json", {"status": "failed", "error": str(exc)})
        raise


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt("received signal " + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted; the experiment cluster has been stopped.", file=sys.stderr)
        sys.exit(130)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
