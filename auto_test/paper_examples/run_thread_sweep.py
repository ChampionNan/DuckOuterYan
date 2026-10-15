#!/usr/bin/env python3
"""Measure one paper query across thread counts, without comparing query results."""

import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from run_forced_order import inspect_profile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def save_report(out, report):
    temporary = out / "comparison.json.tmp"
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(out / "comparison.json")
    lines = ["# Paper query thread sweep", "",
             f"State: {report['state']}; runs/mode: {report['runs']}; correctness: SKIPPED.",
             "Threads are set with SET threads=N; CPU affinity is inherited, with no explicit pinning.", "",
             "| Threads | OFF ms | ON ms | OFF / ON | ON selected | Reordered |",
             "|---:|---:|---:|---:|---|---|"]
    for result in report["results"]:
        numbers = [f"{result[key]:.3f}" if key in result else "—"
                   for key in ("off_median_ms", "on_median_ms", "speedup")]
        decision = result.get("decision", {})
        lines.append(f"| {result['threads']} | {' | '.join(numbers)} | "
                     f"{decision.get('selected_plan', 'ERROR')} | {decision.get('outer_reordered', '—')} |")
    for result in report["results"]:
        if "error" in result:
            lines.extend(["", f"Threads {result['threads']}: {result['error']}"])
    lines.extend(["", report["timing_method"], "", "See comparison.json and each run's result.json for raw samples."])
    (out / "summary.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", type=Path,
                        default=HERE / "tpch/orders_before_july_1998_receipts_over_100_days_late.sql")
    parser.add_argument("--db", type=Path, default=ROOT / "tpch_db")
    parser.add_argument("--bin", type=Path, default=ROOT / "build/release/duckdb")
    parser.add_argument("--threads", type=int, nargs="+", default=[1, 2, 4, 8, 16, 32])
    parser.add_argument("--runs", type=int, default=11)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if min(args.threads + [args.runs, args.timeout]) < 1 or len(set(args.threads)) != len(args.threads):
        parser.error("Use positive runs/timeout and unique positive thread counts")
    for name in ("query", "db", "bin"):
        path = getattr(args, name).resolve()
        if not path.is_file():
            parser.error(f"Missing {name}: {path}")
        setattr(args, name, path)
    out = (args.out or ROOT / "auto_test/results" / (
        "paper_thread_sweep_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    )).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "state": "running", "query": str(args.query), "sql": args.query.read_text(),
        "database": str(args.db), "binary": str(args.bin), "thread_counts": args.threads,
        "runs": args.runs, "correctness": "SKIPPED", "results": [],
        "platform": platform.platform(), "logical_cpu_count": os.cpu_count(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "timing_method": "Thread counts run sequentially. Each uses the single-example harness: "
                         "bare SELECT fully drained, 11 timed runs/mode by default, two process batches "
                         "with reversed mode order and two warm-ups per batch, tracing/profiling off "
                         "during timing. Result comparison skipped; executed plans checked separately.",
    }
    if shutil.which("lscpu"):
        cpu = subprocess.run(["lscpu"], capture_output=True, text=True, check=False)
        report["lscpu"] = cpu.stdout
    save_report(out, report)
    for threads in args.threads:
        report["current_threads"] = threads
        save_report(out, report)
        destination = out / f"threads_{threads}"
        command = [sys.executable, str(HERE / "run_example.py"),
                   "--query", str(args.query), "--db", str(args.db), "--bin", str(args.bin),
                   "--threads", str(threads), "--runs", str(args.runs), "--timeout", str(args.timeout),
                   "--skip-correctness", "--out", str(destination)]
        print(f"Starting threads={threads}", flush=True)
        completed = subprocess.run(command, check=False)
        entry = {"threads": threads, "command": command, "artifacts": str(destination),
                 "exit_code": completed.returncode}
        if completed.returncode:
            entry["error"] = "Single-example runner failed; see its artifacts"
        else:
            try:
                result = json.loads((destination / "result.json").read_text())
                off, on = (result["modes"][mode] for mode in ("off", "on"))
                if any(mode["correctness"] != "SKIPPED" for mode in (off, on)):
                    raise RuntimeError("Unexpected correctness comparison")
                decision = on["decision"]
                reordered = decision.get("selected_plan") == "OUTERYAN" and decision.get("outer_reordered") == "1"
                groups = {}
                for mode, pair in (("off", ("orders", "lineitem")),
                                   ("on", ("customer", "orders") if reordered else ("orders", "lineitem"))):
                    profile = json.loads((destination / f"{mode}.profile.json").read_text())
                    groups[mode] = inspect_profile(profile, pair)
                entry.update(off_median_ms=off["median_seconds"] * 1000,
                             on_median_ms=on["median_seconds"] * 1000,
                             speedup=on["speedup_off_over_mode"], decision=decision,
                             correctness="SKIPPED", physical_groupings=groups,
                             off_seconds=off["seconds"], on_seconds=on["seconds"],
                             off_rows=off["rows"], on_rows=on["rows"],
                             binary_sha256=result["binary_sha256"], tables=result["tables"])
            except (KeyError, ValueError, OSError, RuntimeError) as error:
                entry["error"] = str(error)
        report["results"].append(entry)
        save_report(out, report)
        print(f"Finished threads={threads}: " + json.dumps({k: v for k, v in entry.items()
              if k in ("off_median_ms", "on_median_ms", "speedup", "error")}), flush=True)
    report.pop("current_threads", None)
    failed = any("error" in result for result in report["results"])
    report["state"] = "failed" if failed else "complete"
    save_report(out, report)
    print((out / "summary.md").read_text(), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
