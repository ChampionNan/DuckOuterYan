#!/usr/bin/env python3
"""
OuterYan semi-join pre-filter — performance comparison script.

Measures execution time of outer-join queries under three modes and
computes speedup = baseline_time / mode_time for each.

Three modes
-----------
BITMAP    SET VARIABLE outer_yan_bitmap_max_bytes = 16777216;
          SET disabled_optimizers TO '';
          → KeyBitmap elected for integer/date join keys within byte budget.

HASH      SET VARIABLE outer_yan_bitmap_max_bytes = 0;
          SET disabled_optimizers TO '';
          → HashFilter forced for every key type (budget = 0 disables bitmap).

BASELINE  SET disabled_optimizers TO 'outer_yan_pre,outer_yan_dp,outer_yan_post';
          → DuckDB's own hash-join executes the outer join without any
            SJBuild/SJProbe pre-filtering (the reference point).

Why the pre-filter helps
------------------------
OuterYan's SJBuild materialises the join-key set from relation A.
SJProbe then narrows relation B (the non-preserved side) to only rows
whose key appears in A BEFORE B enters the hash-join's build phase.

When many B rows do NOT match any A row (high filter rate), the hash
table built by the outer join is much smaller, and fewer probe
comparisons are needed.  Speedup is proportional to the filter rate.

Benchmark suites
----------------
TPC-H sf=N   Five outer-join rewrites of TPC-H queries at a given scale
             factor.  Run with --sf 1 (150K customers, 1.5M orders,
             6M lineitems) for a meaningful workload.

Synthetic     fact(1M) LEFT JOIN dim LEFT JOIN anchor.
             dim is kept at 1M rows but with varying key stride, so
             only a controlled fraction of dim rows join fact:

               sel100  stride 1   → 100% overlap (0% filtered by SJProbe)
               sel50   stride 2   →  50% overlap (50% filtered)
               sel10   stride 10  →  10% overlap (90% filtered)
               sel01   stride 100 →   1% overlap (99% filtered)

             The expected speedup pattern is:
               sel100 ≈ 1x (no filtering benefit, slight overhead)
               sel50  ≈ 2x
               sel10  ≈ 5–10x
               sel01  ≈ 20–100x  (depends on hash-table + probe cost)

Usage
-----
  # Default (TPC-H sf=1 + synthetic, 5 runs each):
  python benchmark/outer_yan/perf_compare.py

  # Larger scale factor, more runs, CSV output:
  python benchmark/outer_yan/perf_compare.py --sf 10 --runs 10 --output results.csv

  # Synthetic only (no TPC-H extension needed):
  python benchmark/outer_yan/perf_compare.py --synthetic-only

  # Against the custom DuckDB build's Python extension:
  PYTHONPATH=build/release/python python benchmark/outer_yan/perf_compare.py
"""

import argparse
import csv
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass

try:
    import duckdb
except ImportError:
    print(
        "duckdb not found.\n"
        "  pip install duckdb\n"
        "  For the custom fork: PYTHONPATH=build/release/python python ...",
        file=sys.stderr,
    )
    sys.exit(1)


# ── Mode definitions ──────────────────────────────────────────────────────────

MODES: dict[str, list[str]] = {
    "bitmap": [
        "SET VARIABLE outer_yan_bitmap_max_bytes = 16777216",
        "SET disabled_optimizers TO ''",
    ],
    "hash": [
        "SET VARIABLE outer_yan_bitmap_max_bytes = 0",
        "SET disabled_optimizers TO ''",
    ],
    "baseline": [
        "SET disabled_optimizers TO 'outer_yan_pre,outer_yan_dp,outer_yan_post'",
        "SET VARIABLE outer_yan_bitmap_max_bytes = 16777216",
    ],
}


def apply_mode(con: "duckdb.DuckDBPyConnection", mode: str) -> None:
    for stmt in MODES[mode]:
        con.execute(stmt)


# ── Timing helpers ────────────────────────────────────────────────────────────

@dataclass
class RunResult:
    suite: str
    label: str
    mode: str
    min_s: float
    median_s: float
    mean_s: float


def time_query(
    con: "duckdb.DuckDBPyConnection",
    sql: str,
    n_runs: int,
    n_warmup: int = 1,
) -> tuple[float, float, float]:
    """Execute sql n_warmup + n_runs times; return (min, median, mean) of the timed runs."""
    for _ in range(n_warmup):
        con.execute(sql).fetchall()
    samples: list[float] = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        con.execute(sql).fetchall()
        samples.append(time.perf_counter() - t0)
    return min(samples), statistics.median(samples), statistics.mean(samples)


def run_suite(
    con: "duckdb.DuckDBPyConnection",
    suite_name: str,
    queries: dict[str, str],
    n_runs: int,
    n_warmup: int,
) -> list[RunResult]:
    results: list[RunResult] = []
    for label, sql in queries.items():
        print(f"  {label} ...", flush=True)
        for mode in ("bitmap", "hash", "baseline"):
            apply_mode(con, mode)
            lo, med, mean = time_query(con, sql, n_runs, n_warmup)
            results.append(RunResult(suite_name, label, mode, lo, med, mean))
    return results


# ── TPC-H suite ───────────────────────────────────────────────────────────────

TPCH_QUERIES: dict[str, str] = {
    "q1 customer→orders→lineitem": """
        SELECT c_custkey,
               COUNT(o_orderkey)    AS order_count,
               COUNT(l_linenumber)  AS line_count,
               SUM(l_extendedprice) AS revenue
        FROM customer
        LEFT JOIN orders   ON c_custkey  = o_custkey
        LEFT JOIN lineitem ON o_orderkey = l_orderkey
        GROUP BY c_custkey
    """,
    "q2 nation→supplier→lineitem": """
        SELECT n_name,
               COUNT(s_suppkey)    AS supplier_count,
               COUNT(l_linenumber) AS line_count,
               SUM(l_quantity)     AS total_qty
        FROM nation
        LEFT JOIN supplier ON n_nationkey = s_nationkey
        LEFT JOIN lineitem ON s_suppkey   = l_suppkey
        GROUP BY n_name
    """,
    "q3 q1 + WHERE mktsegment": """
        SELECT c_custkey,
               COUNT(o_orderkey)                          AS order_count,
               SUM(l_extendedprice * (1 - l_discount))   AS net_revenue
        FROM customer
        LEFT JOIN orders   ON c_custkey  = o_custkey
        LEFT JOIN lineitem ON o_orderkey = l_orderkey
        WHERE c_mktsegment = 'BUILDING'
        GROUP BY c_custkey
    """,
    "q4 customer→orders→lineitem→supplier": """
        SELECT c_custkey,
               COUNT(DISTINCT o_orderkey)   AS order_count,
               COUNT(DISTINCT l_linenumber) AS line_count,
               COUNT(DISTINCT s_suppkey)    AS supplier_count
        FROM customer
        LEFT JOIN orders   ON c_custkey  = o_custkey
        LEFT JOIN lineitem ON o_orderkey = l_orderkey
        LEFT JOIN supplier ON l_suppkey  = s_suppkey
        GROUP BY c_custkey
    """,
    "q5 partsupp→part→supplier": """
        SELECT ps_partkey,
               COUNT(DISTINCT ps_suppkey) AS supplier_count,
               SUM(ps_availqty)           AS total_avail,
               MIN(ps_supplycost)         AS min_cost
        FROM partsupp
        LEFT JOIN part     ON ps_partkey = p_partkey
        LEFT JOIN supplier ON ps_suppkey = s_suppkey
        GROUP BY ps_partkey
    """,
}


def setup_tpch(con: "duckdb.DuckDBPyConnection", sf: float) -> None:
    print(f"Loading TPC-H sf={sf} (takes a moment) ...", flush=True)
    con.execute(f"CALL dbgen(sf={sf})")


# ── Synthetic selectivity suite ───────────────────────────────────────────────
#
# Outer join: fact(1M) LEFT JOIN dim LEFT JOIN anchor
#
#   fact  : 1M rows, id 1..1M       — preserved side (outer join keeps all)
#   anchor: 1M rows, id 1..1M       — 100% overlap, always joins
#   dim   : 1M rows, id = stride*i  — overlap controlled by stride:
#
#     sel100  stride=1   → ids 1..1M       → 100% match fact → 0% filtered
#     sel50   stride=2   → ids 2,4..2M    →  50% match fact → 50% filtered
#     sel10   stride=10  → ids 10..10M    →  10% match fact → 90% filtered
#     sel01   stride=100 → ids 100..100M  →   1% match fact → 99% filtered
#
# SJProbe (built from fact's keys) removes the non-matching dim rows BEFORE
# they enter the hash-join's build phase.  The hash table is then:
#   sel100 → 1M entries (no reduction)
#   sel50  → 500K entries (2x smaller)
#   sel10  → 100K entries (10x smaller)
#   sel01  →  10K entries (100x smaller)

_SYN_SETUP_TEMPLATE = """
CREATE OR REPLACE TABLE fact   AS SELECT i        AS id, (i*7) % 1000000 AS val
                                   FROM range(1, 1000001) t(i);
CREATE OR REPLACE TABLE anchor AS SELECT i        AS id, i AS aid
                                   FROM range(1, 1000001) t(i);
CREATE OR REPLACE TABLE dim_sel100 AS SELECT i*1   AS id, i*3 AS attr FROM range(1, 1000001) t(i);
CREATE OR REPLACE TABLE dim_sel50  AS SELECT i*2   AS id, i*3 AS attr FROM range(1, 1000001) t(i);
CREATE OR REPLACE TABLE dim_sel10  AS SELECT i*10  AS id, i*3 AS attr FROM range(1, 1000001) t(i);
CREATE OR REPLACE TABLE dim_sel01  AS SELECT i*100 AS id, i*3 AS attr FROM range(1, 1000001) t(i);
"""

def _syn_q(dim: str) -> str:
    return f"""
        SELECT fact.id,
               COUNT({dim}.attr)  AS attr_count,
               COUNT(anchor.aid)  AS anchor_count
        FROM fact
        LEFT JOIN {dim}  ON fact.id = {dim}.id
        LEFT JOIN anchor ON fact.id = anchor.id
        GROUP BY fact.id
    """

SYNTHETIC_QUERIES: dict[str, str] = {
    "sel=100% (0% filtered,  expect ≈1x)":   _syn_q("dim_sel100"),
    "sel=50%  (50% filtered, expect ≈2x)":    _syn_q("dim_sel50"),
    "sel=10%  (90% filtered, expect ≈5-10x)": _syn_q("dim_sel10"),
    "sel=1%   (99% filtered, expect ≈10-100x)":_syn_q("dim_sel01"),
}


def setup_synthetic(con: "duckdb.DuckDBPyConnection") -> None:
    print("Creating synthetic tables (1M rows × 6 tables) ...", flush=True)
    # Execute each CREATE statement separately.
    for stmt in _SYN_SETUP_TEMPLATE.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_report(results: list[RunResult]) -> None:
    grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for r in results:
        grouped[(r.suite, r.label)][r.mode] = r.median_s

    col = [45, 10, 10, 11, 14, 14]
    header = ["Query", "Bitmap(s)", "Hash(s)", "Baseline(s)", "Spdup-Bitmap", "Spdup-Hash"]
    sep = "  ".join("-" * w for w in col)
    print()
    print("  ".join(h.ljust(w) for h, w in zip(header, col)))
    print(sep)

    prev_suite = None
    for (suite, label), times in grouped.items():
        if suite != prev_suite:
            if prev_suite is not None:
                print()
            print(f"── {suite} ──")
            prev_suite = suite

        bm   = times.get("bitmap",   float("inf"))
        ha   = times.get("hash",     float("inf"))
        base = times.get("baseline", float("inf"))

        def _spd(t: float) -> str:
            return f"{base/t:.2f}x" if t > 0 else "—"

        row = [label, f"{bm:.4f}", f"{ha:.4f}", f"{base:.4f}", _spd(bm), _spd(ha)]
        print("  ".join(v.ljust(w) for v, w in zip(row, col)))

    print()
    print("Speedup = baseline / mode  (>1x = OuterYan faster than DuckDB's own hash-join)")
    print("Times are medians across all timed runs.")
    print()
    print("Key: OuterYan inserts SJBuild/SJProbe operators into the join tree.")
    print("     SJProbe pre-filters the non-preserved side before hash-table build.")
    print("     Benefit scales with filter rate: more rows removed → larger speedup.")


def save_csv(results: list[RunResult], path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["suite", "label", "mode", "min_s", "median_s", "mean_s"])
        for r in results:
            w.writerow([r.suite, r.label, r.mode,
                        f"{r.min_s:.6f}", f"{r.median_s:.6f}", f"{r.mean_s:.6f}"])
    print(f"Results written to {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="OuterYan SJ pre-filter perf: bitmap vs hash vs DuckDB baseline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--sf",            type=float, default=1.0,
                    help="TPC-H scale factor (default 1)")
    ap.add_argument("--runs",          type=int,   default=5,
                    help="Timed runs per (query, mode) (default 5)")
    ap.add_argument("--warmup",        type=int,   default=1,
                    help="Warmup runs before timing (default 1)")
    ap.add_argument("--output",        type=str,   default=None,
                    help="CSV output path")
    ap.add_argument("--tpch-only",     action="store_true",
                    help="Skip synthetic queries (only TPC-H)")
    ap.add_argument("--synthetic-only",action="store_true",
                    help="Skip TPC-H (only synthetic; no extension needed)")
    args = ap.parse_args()

    con = duckdb.connect()
    all_results: list[RunResult] = []

    if not args.synthetic_only:
        setup_tpch(con, args.sf)
        label = f"TPC-H sf={args.sf}"
        print(f"\n{label} — {args.runs} timed runs + {args.warmup} warmup per (query, mode)")
        all_results += run_suite(con, label, TPCH_QUERIES, args.runs, args.warmup)

    if not args.tpch_only:
        setup_synthetic(con)
        label = "Synthetic 1M rows"
        print(f"\n{label} — {args.runs} timed runs + {args.warmup} warmup per (query, mode)")
        all_results += run_suite(con, label, SYNTHETIC_QUERIES, args.runs, args.warmup)

    print_report(all_results)

    if args.output:
        save_csv(all_results, args.output)


if __name__ == "__main__":
    main()
