#!/usr/bin/env python3
"""Check that every generated workload entry reaches OuterYan DP, using EXPLAIN only."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "auto_test" / "outerjoin_benchmark"
CORPORA = (
    "benchmark", "v2/benchmark", "v3/benchmark",
    "v3/selectivity_stress", "v2/job_regressions",
)


def audit_query(binary, database, query, trace, timeout):
    trace.write_text("", encoding="utf-8")
    env = os.environ.copy()
    for name in ("DUCKDB_OY_FORCE_CANDIDATE", "DUCKDB_OY_SIMPLIFY_SCAN_FILTERS", "DUCKDB_OY_PROFILE_TRACE"):
        env.pop(name, None)
    env["DUCKDB_OYTRACE"] = str(trace)
    sql = (
        f"SET threads=4; SET max_execution_time={timeout * 1000}; "
        "SET disabled_optimizers=''; EXPLAIN " + query.read_text(encoding="utf-8")
    )
    try:
        result = subprocess.run(
            [str(binary), "-readonly", "-no-init", "-bail", str(database)],
            input=sql, text=True, capture_output=True, timeout=timeout + 5, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"dp_complete": False, "error": "EXPLAIN timeout"}
    if result.returncode:
        return {"dp_complete": False, "error": result.stderr.strip()}
    records = [line for line in trace.read_text(encoding="utf-8").splitlines()
               if line.startswith("[OY_DECISION] ")]
    if len(records) != 1:
        return {"dp_complete": False, "error": f"expected one decision, found {len(records)}"}
    fields = dict(token.split("=", 1) for token in records[0].split()[1:])
    reason = fields.get("reason", "")
    ran_dp = float(fields.get("phase_outeryan_join_reorder_s", "0")) > 0
    return {
        "dp_complete": ran_dp and reason not in ("INAPPLICABLE", "OUTERYAN_FAILED"),
        "reason": reason,
        "selected_plan": fields.get("selected_plan"),
        "outer_reordered": fields.get("outer_reordered"),
        "dp_seconds": fields.get("phase_outeryan_join_reorder_s"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb", type=Path, default=Path(os.environ.get("DUCKDB_BIN", ROOT / "build/release/duckdb")))
    parser.add_argument("--corpus", choices=CORPORA, action="append", help="default: all generated suites")
    parser.add_argument("--timeout", type=int, default=15, help="per-EXPLAIN timeout in seconds")
    parser.add_argument("--out", type=Path, required=True, help="JSON coverage report")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    rows = []
    with tempfile.TemporaryDirectory(prefix="outeryan-dp-") as scratch:
        trace = Path(scratch) / "decision.trace"
        for corpus in args.corpus or CORPORA:
            queries = sorted((CORPUS_ROOT / corpus).rglob("*.sql"))
            if not queries:
                parser.error(f"no queries found for {corpus}")
            for query in queries:
                family = query.parent.name
                database = Path(os.environ.get(f"{family.upper()}_DB", ROOT / f"{family}_db"))
                row = audit_query(args.duckdb.resolve(), database.resolve(), query, trace, args.timeout)
                rows.append({"corpus": corpus, "query": str(query.relative_to(CORPUS_ROOT)), **row})
                if not row["dp_complete"]:
                    detail = row.get("error", row.get("reason", "no complete DP plan"))
                    print(f"FAIL {query.name}: {detail.splitlines()[0]}", flush=True)
            subset = [row for row in rows if row["corpus"] == corpus]
            complete = sum(row["dp_complete"] for row in subset)
            print(f"{corpus}: {complete}/{len(subset)} reached DP; "
                  f"decisions={dict(Counter(row.get('reason', 'ERROR') for row in subset))}", flush=True)
    failures = sum(not row["dp_complete"] for row in rows)
    report = {"queries": len(rows), "dp_complete": len(rows) - failures, "failures": failures, "rows": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"DP coverage: {len(rows) - failures}/{len(rows)}; report: {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
