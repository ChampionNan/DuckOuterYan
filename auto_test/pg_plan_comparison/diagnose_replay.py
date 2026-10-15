#!/usr/bin/env python3
"""Read-only ablations of existing PG replay artifacts; never regenerate data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess


MODES = {
    "PG-Replay": "outer_yan",
    "PG-Replay-no-unused": "outer_yan,unused_columns",
    "DuckDB": "outer_yan",
    "DuckDB-no-stats": "outer_yan,statistics_propagation",
    "DuckDB-no-join-filter": "outer_yan,join_filter_pushdown",
    "DuckDB-no-compression": "outer_yan,compressed_materialization",
}


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb", type=Path, required=True)
    parser.add_argument("--source-results", type=Path, required=True)
    parser.add_argument("--job-db", type=Path)
    parser.add_argument("--tpch-db", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=["a", "b"], default=["a"])
    parser.add_argument("--modes", nargs="+", choices=list(MODES), default=list(MODES))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    binary = args.duckdb.resolve()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("DUCKDB_OY", "DUCKDB_SJ"))}
    manifest = {"binary": str(binary), "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "threads": 1, "memory_limit": "4GB", "repeats": args.repeats,
                "timing": "unprofiled bare SELECT; full result drain; seeded interleaving",
                "correctness": "diagnostic ablation only; profiles record cardinality, not exact multiset equality",
                "cases": {}}
    (args.out / "environment.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def execute(db, sql, stem):
        stem.with_suffix(".sql").write_text(sql)
        with stem.with_suffix(".stdout").open("w") as stdout, stem.with_suffix(".stderr").open("w") as stderr:
            subprocess.run([str(binary), str(db), "-readonly", "-init", os.devnull, "-batch", "-bail"],
                           input=sql, text=True, stdout=stdout, stderr=stderr,
                           env=env, timeout=args.timeout, check=True)

    for case in args.cases:
        db = args.job_db if case == "a" else args.tpch_db
        if not db:
            parser.error("missing database path for case " + case)
        db = db.resolve()
        before = db.stat()
        source = args.source_results.resolve() / ("case_" + case)
        query = (source / "query.sql").read_text()
        artifact = source / "pg_replay.json"
        case_out = args.out / ("case_" + case)
        case_out.mkdir()
        (case_out / "query.sql").write_text(query)

        def setup(mode):
            sql = ".timer off\n.mode trash\nSET threads=1;\nSET memory_limit='4GB';\n"
            sql += "RESET VARIABLE pgplan;\nRESET VARIABLE outer_yan_pg_replay_plan;\n"
            sql += "SET disabled_optimizers TO " + literal(MODES[mode]) + ";\n"
            if mode.startswith("PG-Replay"):
                sql += "SET VARIABLE pgplan=" + literal(artifact) + ";\n"
            return sql

        for mode in args.modes:
            print("profile", case, mode, flush=True)
            sql = setup(mode) + "PRAGMA enable_profiling='json';\n"
            sql += "PRAGMA profiling_output=" + literal(case_out / (mode + ".profile.json")) + ";\n" + query
            execute(db, sql, case_out / (mode + ".profile"))

        # A separate warm-up for every mode, followed by interleaved timed bare queries.
        sql = ""
        for mode in args.modes:
            sql += setup(mode) + query + "\n"
        order = []
        rng = random.Random(20261003)
        for iteration in range(args.repeats):
            modes = list(args.modes)
            rng.shuffle(modes)
            for mode in modes:
                order.append({"mode": mode, "iteration": iteration})
                sql += setup(mode) + ".timer on\n" + query + "\n.timer off\n"
        print("timing", case, len(order), "queries", flush=True)
        execute(db, sql, case_out / "timing")
        output = (case_out / "timing.stdout").read_text()
        times = [float(v) for v in re.findall(r"Run Time \(s\): real ([0-9.]+)", output)]
        if len(times) != len(order):
            raise RuntimeError("timer count mismatch: %d != %d" % (len(times), len(order)))
        for sample, seconds in zip(order, times):
            sample["seconds"] = seconds
        summary = {mode: statistics.median(s["seconds"] for s in order if s["mode"] == mode)
                   for mode in args.modes}
        (case_out / "timing_samples.json").write_text(json.dumps(order, indent=2) + "\n")
        (case_out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        after = db.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("database changed during diagnosis")
        manifest["cases"][case] = {"database": str(db), "size": before.st_size,
                                    "mtime_ns": before.st_mtime_ns, "summary_seconds": summary}
        (args.out / "environment.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
