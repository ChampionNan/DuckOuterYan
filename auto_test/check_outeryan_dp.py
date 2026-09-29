#!/usr/bin/env python3
"""Check that every generated workload entry reaches OuterYan DP, using EXPLAIN only."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "auto_test" / "outerjoin_benchmark"
CORPORA = ("benchmark",)


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
        # Retain exact gate operands and policy settings for later cost analysis.
        "decision_fields": fields,
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
    binary = args.duckdb.resolve()
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    manifest_hashes = {}
    with tempfile.TemporaryDirectory(prefix="outeryan-dp-") as scratch:
        trace = Path(scratch) / "decision.trace"
        for corpus in args.corpus or CORPORA:
            manifest = CORPUS_ROOT / corpus / "manifest.csv"
            manifest_hashes[corpus] = hashlib.sha256(manifest.read_bytes()).hexdigest()
            with manifest.open(newline="", encoding="utf-8") as handle:
                metadata = {row["path"]: row for row in csv.DictReader(handle)}
            queries = sorted((CORPUS_ROOT / corpus).rglob("*.sql"))
            if not queries:
                parser.error(f"no queries found for {corpus}")
            for query in queries:
                family = query.parent.name
                database = Path(os.environ.get(f"{family.upper()}_DB", ROOT / f"{family}_db"))
                row = audit_query(binary, database.resolve(), query, trace, args.timeout)
                item = metadata[str(query.relative_to(CORPUS_ROOT / corpus))]
                rows.append({"corpus": corpus, "query": str(query.relative_to(CORPUS_ROOT)),
                             "family": family, "semantic_tier": item.get("semantic_tier", "unspecified"),
                             "query_type": item.get("query_class", "custom"),
                             "sql_fingerprint": item.get("sql_fingerprint"),
                             "calibration_fraction": item.get("calibration_fraction"), **row})
                if not row["dp_complete"]:
                    detail = row.get("error", row.get("reason", "no complete DP plan"))
                    print(f"FAIL {query.name}: {detail.splitlines()[0]}", flush=True)
            subset = [row for row in rows if row["corpus"] == corpus]
            complete = sum(row["dp_complete"] for row in subset)
            print(f"{corpus}: {complete}/{len(subset)} reached DP; "
                  f"decisions={dict(Counter(row.get('reason', 'ERROR') for row in subset))}", flush=True)
    failures = sum(not row["dp_complete"] for row in rows)
    main_rows = rows
    def selection_summary(items):
        selected = sum(row.get("selected_plan") == "OUTERYAN" for row in items)
        return {"queries": len(items), "outeryan": selected,
                "duckdb": sum(row.get("selected_plan") == "DUCKDB" for row in items),
                "outeryan_percent": round(100 * selected / len(items), 2) if items else 0.0}
    groups = {field: {key: selection_summary([row for row in main_rows if row[field] == key])
                      for key in sorted({row[field] for row in main_rows})}
              for field in ("query_type", "family", "semantic_tier")}
    selection = selection_summary(main_rows)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != binary_hash:
        raise RuntimeError("DuckDB binary changed during the audit; rerun with a stable binary")
    report = {"queries": len(rows), "dp_complete": len(rows) - failures, "failures": failures,
              "duckdb_binary": str(binary), "duckdb_sha256": binary_hash,
              "manifest_sha256": manifest_hashes,
              "main_selection": selection, "selection_groups": groups,
              "cost_gate_failures": cost_gate_distribution(main_rows),
              "threshold_replay": threshold_replay(main_rows), "rows": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"DP coverage: {len(rows) - failures}/{len(rows)}; report: {args.out}")
    print(f"Main-suite selection: OuterYan {selection['outeryan']}/{selection['queries']} "
          f"({selection['outeryan_percent']:.2f}%); DuckDB {selection['duckdb']}")
    return 1 if failures else 0


def cost_gate_distribution(rows):
    """Use limiting gate operands; exclude same-grouping fallbacks and duplicate guards."""
    rejected = [row for row in rows if row.get("reason") == "COST_DUCKDB_BETTER"]
    ratios, threshold_excess = [], []
    for row in rejected:
        decision = row["decision_fields"]
        lhs, rhs = float(decision["gate_lhs"]), float(decision["gate_rhs"])
        baseline = float(decision["baseline_cost"])
        if not all(math.isfinite(value) and value > 0 for value in (lhs, rhs, baseline)):
            raise ValueError(f"Invalid cost operands for {row['query']}")
        ratios.append(lhs / baseline)
        threshold_excess.append(lhs / rhs - 1)
    def bins(values, upper_bounds):
        output = []
        lower = None
        for upper in (*upper_bounds, None):
            count = sum((lower is None or value > lower) and
                        (upper is None or value <= upper) for value in values)
            output.append({"lower_exclusive": lower, "upper_inclusive": upper, "count": count,
                           "percent": 100 * count / len(values) if values else 0})
            lower = upper
        return output
    def quantile(values, probability):
        if not values:
            return None
        ordered = sorted(values)
        index = (len(ordered) - 1) * probability
        lower, upper = math.floor(index), math.ceil(index)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
    return {
        "rejected": len(rejected),
        "definition": "r = gate_lhs / baseline_cost; threshold_excess = gate_lhs / gate_rhs - 1",
        "semijoin_weights": sorted({float(row["decision_fields"]["semijoin_cost_ratio"]) for row in rejected}),
        "gate_limits": sorted({float(row["decision_fields"]["cost_ratio_limit"]) for row in rejected}),
        "ratio_bins": bins(ratios, (1.2, 1.25, 1.3, 1.5, 2, 5, 10)),
        "threshold_excess_bins": bins(threshold_excess, (.05, .10, .20, .50, 1, 4)),
        "ratio_quantiles": {str(p): quantile(ratios, p) for p in (0, .25, .5, .75, .9, .95, 1)},
    }


def threshold_replay(rows, ceilings=None):
    """Replay wider uniform gates at the recorded SJ weight; never bypass hard guards.

    Changing only the ceiling leaves both DP enumeration and the limiting cost
    scenario unchanged. Changing the SJ weight can change the limiting scenario
    and requires fresh optimizer traces rather than this threshold-only replay.
    """
    current = sum(row.get("selected_plan") == "OUTERYAN" for row in rows)
    failed = [row for row in rows if row.get("reason") == "COST_DUCKDB_BETTER"]
    if ceilings is None:
        recorded_limit = max((float(row["decision_fields"]["cost_ratio_limit"])
                              for row in failed), default=1.20)
        ceilings = sorted({recorded_limit, *(limit for limit in (1.20, 1.25, 1.30, 1.40, 1.50)
                                            if limit >= recorded_limit)})
    output = []
    for ceiling in ceilings:
        extra = []
        for row in failed:
            fields = row["decision_fields"]
            if ceiling < float(fields["cost_ratio_limit"]):
                raise ValueError("Threshold replay only supports wider gates")
            if float(fields["candidate_total"]) <= ceiling * float(fields["baseline_cost"]):
                extra.append(row)
        output.append({
            "uniform_cost_ceiling": ceiling, "additional_outeryan": len(extra),
            "outeryan_total": current + len(extra),
            "outeryan_percent": 100 * (current + len(extra)) / len(rows) if rows else 0,
            "additional_by_family": dict(Counter(row["family"] for row in extra)),
            "additional_queries": [row["query"] for row in extra],
        })
    return {"status": "counterfactual gate replay, not an optimizer rerun or runtime measurement",
            "fixed_parameters": "recorded SJ weight, DP candidate, conservative cost scenarios and hard guards",
            "varied_parameter": "all strict candidate/baseline ceilings, including aggregate and low-retention",
            "rows": output}


if __name__ == "__main__":
    raise SystemExit(main())
