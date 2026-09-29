#!/usr/bin/env python3
"""Run one paper SELECT with the local DuckDB CLI, including fallback plans."""

import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", type=Path, default=HERE / "tpch/customer_orders_lineitem.sql")
    parser.add_argument("--db", type=Path, default=ROOT / "tpch_db")
    parser.add_argument("--bin", type=Path, default=ROOT / "build/release/duckdb")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--runs", type=int, default=9, help="Timed executions per mode after warm-up")
    parser.add_argument("--timeout", type=int, default=120, help="Per-statement limit in seconds")
    parser.add_argument("--force-candidate", action="store_true", help="Also run diagnostic forced ON")
    parser.add_argument("--out", type=Path, help="New result directory (must not already exist)")
    args = parser.parse_args()
    if min(args.threads, args.runs, args.timeout) < 1:
        parser.error("threads, runs and timeout must be positive")
    for name in ("query", "db", "bin"):
        path = getattr(args, name).resolve()
        if not path.is_file():
            parser.error(f"{name} file does not exist: {path}")
        setattr(args, name, path)

    query = args.query.read_text().strip()
    if not query.endswith(";"):
        query += ";"
    out = (args.out or ROOT / "auto_test/results" / (
        "paper_" + args.query.stem + "_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    )).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "query.sql").write_text(query + "\n")
    modes = ["off", "on"] + (["forced"] if args.force_candidate else [])
    env = os.environ.copy()
    # Keep diagnostic output and force overrides out of the normal/timed runs.
    for key in list(env):
        if key.startswith("DUCKDB_OY") or key == "DUCKDB_SJ_KERNEL_TRACE":
            env.pop(key)

    def setup(mode):
        disabled = "outer_yan" if mode == "off" else ""
        return (
            ".timer off\n.mode trash\nCALL disable_profiling();\n"
            f"SET threads={args.threads}; SET max_execution_time={args.timeout * 1000};\n"
            f"SET disabled_optimizers='{disabled}';\n"
        )

    def run(label, sql, mode="off", trace=False, executions=1):
        child_env = env.copy()
        if mode == "forced":
            child_env["DUCKDB_OY_FORCE_CANDIDATE"] = "1"
        if trace:
            child_env["DUCKDB_OYTRACE"] = str(out / f"{label}.trace.txt")
        (out / f"{label}.sql").write_text(sql)
        with (out / f"{label}.stdout.txt").open("w") as stdout, (
            out / f"{label}.stderr.txt"
        ).open("w") as stderr:
            subprocess.run(
                [str(args.bin), "-readonly", "-no-init", "-bail", str(args.db)],
                input=sql, text=True, stdout=stdout, stderr=stderr, env=child_env,
                check=True, timeout=args.timeout * executions + 30,
            )
        return (out / f"{label}.stdout.txt").read_text()

    metadata = json.loads(run("metadata", setup("off") + ".mode json\n" +
        "SELECT table_name, estimated_size FROM duckdb_tables() WHERE schema_name='main';\n"))
    report = {
        "query": str(args.query), "database": str(args.db), "binary": str(args.bin),
        "binary_sha256": hashlib.sha256(args.bin.read_bytes()).hexdigest(),
        "platform": platform.platform(), "threads": args.threads, "runs": args.runs,
        "tables": metadata, "modes": {},
        "timing_method": "Bare SELECT, profiling/traces off, CLI trash mode, two warm-ups; "
                         "alternating mode order across two batches; includes optimization and result draining.",
    }

    # EXPLAIN shows final physical plans; tracing records candidate grouping and selection.
    for mode in modes:
        label = f"{mode}.explain"
        raw = run(label, setup(mode) + ".mode json\nPRAGMA explain_output='all';\nEXPLAIN " + query,
                  mode, trace=mode != "off")
        (out / f"{mode}.plan.txt").write_text(raw)
        decision = {}
        if mode != "off":
            records = [line for line in (out / f"{label}.trace.txt").read_text().splitlines()
                       if line.startswith("[OY_DECISION] ")]
            if not records:
                raise RuntimeError(f"Missing OuterYan decision for {mode}")
            decision = dict(token.split("=", 1) for token in records[-1].split()[1:])
        report["modes"][mode] = {"decision": decision}
        print(f"{mode}: selected={decision.get('selected_plan', 'DUCKDB')} "
              f"reordered={decision.get('outer_reordered', 'n/a')} "
              f"reason={decision.get('reason', 'outer_yan disabled')}", flush=True)

    # Compare complete CSV record multisets, preserving duplicates and embedded newlines.
    # This single-example runner intentionally uses memory proportional to the result.
    baseline = None
    for mode in modes:
        label = f"{mode}.correctness"
        try:
            run(label, setup(mode) + ".mode csv\n.headers off\n.nullvalue __PAPER_SQL_NULL__\n" + query,
                mode, trace=mode != "off")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            detail = (out / f"{label}.stderr.txt").read_text().strip()
            report["modes"][mode].update(correctness="ERROR", error=detail or str(error))
            print(f"{mode}: correctness ERROR; timing skipped ({detail.splitlines()[0] if detail else error})",
                  flush=True)
            if mode == "off":
                (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
                raise
            continue
        if mode != "off":
            records = [line for line in (out / f"{label}.trace.txt").read_text().splitlines()
                       if line.startswith("[OY_DECISION] ")]
            actual = dict(token.split("=", 1) for token in records[-1].split()[1:])
            for key in ("selected_plan", "outer_reordered", "reason"):
                if actual[key] != report["modes"][mode]["decision"][key]:
                    raise RuntimeError(f"Bare query and EXPLAIN disagree: {mode} {key}")
        with (out / f"{label}.stdout.txt").open(newline="") as source:
            rows = collections.Counter(tuple(row) for row in csv.reader(source))
        if baseline is None:
            baseline = rows
        elif rows != baseline:
            report["modes"][mode].update(correctness="FAIL", error="Result multiset differs from OFF")
            print(f"{mode}: correctness FAIL; timing skipped", flush=True)
            continue
        report["modes"][mode]["rows"] = sum(rows.values())
        report["modes"][mode]["correctness"] = "PASS"
        print(f"{mode}: correctness PASS ({sum(rows.values())} rows)", flush=True)
        (out / f"{label}.stdout.txt").unlink()
    del baseline, rows
    valid_modes = [mode for mode in modes if report["modes"][mode]["correctness"] == "PASS"]

    # Two separate processes per mode, reversing order in batch two. Each warms
    # its own buffer pool twice. No EXPLAIN, tracing, output formatting or CTAS.
    samples = {mode: [] for mode in valid_modes}
    counts = [(args.runs + 1) // 2, args.runs // 2]
    for batch, count in enumerate(counts):
        if not count:
            continue
        order = valid_modes if batch == 0 else list(reversed(valid_modes))
        for mode in order:
            label = f"{mode}.timing{batch + 1}"
            raw = run(label, setup(mode) + ".timer on\n" + (query + "\n") * (count + 2),
                      mode, executions=count + 2)
            times = [float(value) for value in re.findall(r"Run Time.*?real\s+([0-9.]+)", raw)]
            if len(times) != count + 2:
                raise RuntimeError(f"Incomplete timing batch: {label}")
            samples[mode].extend(times[2:])
    for mode in valid_modes:
        report["modes"][mode]["seconds"] = samples[mode]
        report["modes"][mode]["median_seconds"] = statistics.median(samples[mode])
        report["modes"][mode]["speedup_off_over_mode"] = (
            statistics.median(samples["off"]) / statistics.median(samples[mode])
        )

    # Profiles are separate from timing and retain actual cardinalities/operator times.
    for mode in valid_modes:
        profile_path = str(out / f"{mode}.profile.json").replace("'", "''")
        run(f"{mode}.profile", setup(mode) + query + "\n" +
            f"CALL enable_profiling(format='json', save_location='{profile_path}');\n" + query,
            mode, executions=2)

    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Single paper example", "", f"Threads: {args.threads}; timed runs/mode: {args.runs}.",
             "", "| Mode | Selected | Reordered | Correctness | Rows | Median ms | OFF / mode |",
             "|---|---|---|---|---:|---:|---:|"]
    for mode, result in report["modes"].items():
        decision = result["decision"]
        median = f"{result['median_seconds'] * 1000:.3f}" if mode in valid_modes else "—"
        speedup = f"{result['speedup_off_over_mode']:.3f}" if mode in valid_modes else "—"
        lines.append(f"| {mode} | {decision.get('selected_plan', 'DUCKDB')} | "
                     f"{decision.get('outer_reordered', 'n/a')} | {result['correctness']} | "
                     f"{result.get('rows', '—')} | {median} | {speedup} |")
    lines += ["", "Only modes whose result multisets match OFF are timed. "
              "Forced mode is diagnostic, not default selection.",
              "", report["timing_method"], "", "See result.json for raw samples and selection reasons."]
    for mode in modes:
        if "error" in report["modes"][mode]:
            lines += ["", f"{mode}: {report['modes'][mode]['error'].splitlines()[0]}"]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"\nArtifacts: {out}")
    return 0 if len(valid_modes) == len(modes) else 1


if __name__ == "__main__":
    sys.exit(main())
