#!/usr/bin/env python3
"""Compare four fixed paper examples using bare SELECT timings and optional result checks."""

import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys

from run_forced_order import inspect_profile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATES = (
    "orders_before_1997_receipts_over_90_days_late",
    "orders_before_1997_receipts_over_90_days_late_date_difference",
    "orders_before_1997_receipts_over_100_days_late",
    "orders_before_july_1998_receipts_over_100_days_late",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "tpch_db")
    parser.add_argument("--bin", type=Path, default=ROOT / "build/release/duckdb")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--runs", type=int, default=11)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--min-speedup", type=float, default=1.4)
    parser.add_argument("--skip-correctness", action="store_true", help="Skip full result comparison")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.runs < 11 or min(args.threads, args.timeout) < 1 or not args.min_speedup >= 1:
        parser.error("Use at least 11 runs, positive threads/timeout, and a speedup target >= 1")
    for name in ("db", "bin"):
        path = getattr(args, name).resolve()
        if not path.is_file():
            parser.error(f"Missing {name}: {path}")
        setattr(args, name, path)
    out = (args.out or ROOT / "auto_test/results" / (
        "paper_sf100_candidates_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    )).resolve()
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for name in CANDIDATES:
        destination = out / name
        command = [sys.executable, str(HERE / "run_example.py"),
                   "--query", str(HERE / "tpch" / (name + ".sql")),
                   "--db", str(args.db), "--bin", str(args.bin),
                   "--threads", str(args.threads), "--runs", str(args.runs),
                   "--timeout", str(args.timeout), "--out", str(destination)]
        if args.skip_correctness:
            command.append("--skip-correctness")
        print(f"\nValidating {name}", flush=True)
        completed = subprocess.run(command, check=False)
        entry = {"query": name, "artifacts": str(destination), "command": command,
                 "exit_code": completed.returncode, "required_speedup": args.min_speedup,
                 "sf100_target_met": False}
        if completed.returncode:
            entry["error"] = "Single-example validation failed; see its artifacts"
        else:
            try:
                report = json.loads((destination / "result.json").read_text())
                off, on = (report["modes"][mode] for mode in ("off", "on"))
                counts = {table["table_name"]: table["estimated_size"] for table in report["tables"]}
                sf100 = counts.get("customer") == 15_000_000 and counts.get("orders") == 150_000_000
                entry.update(sf100_table_sizes=sf100, tables=counts,
                             correctness=on["correctness"], rows=on["rows"],
                             off_median_ms=off["median_seconds"] * 1000,
                             on_median_ms=on["median_seconds"] * 1000,
                             speedup=on["speedup_off_over_mode"], decision=on["decision"])
                groups = {}
                for mode, pair in (("off", ("orders", "lineitem")), ("on", ("customer", "orders"))):
                    profile = json.loads((destination / f"{mode}.profile.json").read_text())
                    groups[mode] = inspect_profile(profile, pair)
                entry["physical_groupings"] = groups
                decision = on["decision"]
                expected_correctness = "SKIPPED" if args.skip_correctness else "PASS"
                entry["sf100_target_met"] = (
                    sf100 and off["correctness"] == on["correctness"] == expected_correctness
                    and decision.get("selected_plan") == "OUTERYAN"
                    and decision.get("outer_reordered") == "1"
                    and decision.get("selection_mode") == "GATED"
                    and on["speedup_off_over_mode"] >= args.min_speedup
                )
            except (KeyError, ValueError, OSError, RuntimeError) as error:
                entry["error"] = str(error)
        results.append(entry)
        # Keep completed cases even if a later run is interrupted.
        (out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps({key: value for key, value in entry.items()
                          if key in ("query", "speedup", "sf100_target_met", "error")}), flush=True)
    lines = ["# Fixed paper-candidate comparison", "",
             "Result comparison SKIPPED (--skip-correctness)." if args.skip_correctness
             else "Full result equality checked against OFF.",
             "The performance target requires SF100 table sizes, normal gated selection,",
             f"customer–orders first in the executed profile, and median OFF / ON >= {args.min_speedup}.", "",
             "| Query | Correctness | OFF ms | ON ms | OFF / ON | SF100 target met |",
             "|---|---|---:|---:|---:|---|"]
    for result in results:
        numbers = [f"{result[key]:.3f}" if key in result else "—"
                   for key in ("off_median_ms", "on_median_ms", "speedup")]
        lines.append(f"| {result['query']} | {result.get('correctness', 'ERROR')} | "
                     f"{' | '.join(numbers)} | {result['sf100_target_met']} |")
    for result in results:
        if "error" in result:
            lines.extend(["", f"{result['query']}: {result['error']}"])
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"\nArtifacts: {out}")
    # A missed speedup target is an experimental result, not a runner failure.
    return 1 if any("error" in result for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
