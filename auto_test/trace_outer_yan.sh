#!/usr/bin/env bash
# ============================================================================
# trace_outer_yan.sh
#
# Pipeline recorder for the OuterYan optimizer. For a chosen query it runs the
# bare SELECT once with OuterYan ENABLED and the env var DUCKDB_OYTRACE set, so
# every pass appends a labelled snapshot of what it produced:
#
#   original query  ->  input logical plan  ->  after BuildOT  ->  after
#   Simplify  ->  semi-join pairs (2 passes)  ->  after Desimplify  ->
#   after DP  ->  after Resimplify  ->  after SJ insertion  ->  (agg) after
#   Aggregate Pushdown
#
# OT/OJT stages are rendered verbose (each edge shows kind + was=original_kind
# + PK/elim markers); plan stages are rendered as the logical plan. Comparing
# consecutive snapshots shows exactly which rule rewrote which edge — i.e.
# where a wrong answer is introduced.
#
# Runs the query against an EXISTING database file (graph_db, tpch_db,
# tpcds_db, job_db, ...) — no temp loading. You pass --db PATH.
#
# USAGE:
#   trace_outer_yan.sh --db graph_db fails              # trace 5 known-failing queries
#   trace_outer_yan.sh --db graph_db -q "SELECT ... ;"  # trace one ad-hoc query
#   trace_outer_yan.sh --db tpch_db -q "..." -o out.txt # choose output file
#   options: --db PATH       (REQUIRED) DuckDB database file to query against
#            -b/--bin PATH   duckdb binary (default build/debug/duckdb)
#            -d/--outdir DIR trace dir for `fails` mode (default ./results/oy_traces)
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DUCKDB_BIN="${DUCKDB_BIN:-$REPO_ROOT/build/debug/duckdb}"
OUTDIR="$SCRIPT_DIR/results/oy_traces"
MODE=""
QUERY=""
OUTFILE=""
DB_FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        fails)         MODE="fails"; shift ;;
        -q|--query)    MODE="one"; QUERY="$2"; shift 2 ;;
        -o|--out)      OUTFILE="$2"; shift 2 ;;
        -b|--bin)      DUCKDB_BIN="$2"; shift 2 ;;
        -d|--outdir)   OUTDIR="$2"; shift 2 ;;
        --db)          DB_FILE="$2"; shift 2 ;;
        -h|--help)     sed -n '2,/^set /{/^set /q;p}' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[ -n "$MODE" ]    || { echo "Nothing to do; pass 'fails' or -q \"SQL\". See --help." >&2; exit 2; }
[ -n "$DB_FILE" ] || { echo "Error: --db PATH is required (e.g. --db $REPO_ROOT/graph_db)" >&2; exit 2; }
# Resolve relative path against current working directory
case "$DB_FILE" in /*) ;; *) DB_FILE="$(cd "$(dirname "$DB_FILE")" 2>/dev/null && pwd)/$(basename "$DB_FILE")" ;; esac
[ -f "$DB_FILE" ] || { echo "Error: database file not found: $DB_FILE" >&2; exit 1; }
[ -x "$DUCKDB_BIN" ] || { echo "Error: duckdb binary not found: $DUCKDB_BIN" >&2; exit 1; }

# Run one bare query ON with the tracer writing to $2 (truncated first).
trace_one() {  # $1=query  $2=outfile
    : > "$2"
    { echo "SET disabled_optimizers TO '';"; echo "$1"; } \
        | DUCKDB_OYTRACE="$2" "$DUCKDB_BIN" "$DB_FILE" >/dev/null 2>&1
    echo "  wrote $(wc -l < "$2" | tr -d ' ') lines -> $2"
}

if [ "$MODE" = "one" ]; then
    OUTFILE="${OUTFILE:-$SCRIPT_DIR/results/oy_trace.txt}"
    echo "Tracing ad-hoc query -> $OUTFILE"
    trace_one "$QUERY" "$OUTFILE"
    echo "============================================================"
    cat "$OUTFILE"
    exit 0
fi

# --- fails mode: the 5 historically failing graph queries --------------
mkdir -p "$OUTDIR"
declare -a NAMES QUERIES
NAMES+=("chain_5rel_LEFT-INNER-FULL-RIGHT")
QUERIES+=("SELECT * FROM R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src INNER JOIN R3 ON R2.dst=R3.src FULL OUTER JOIN R4 ON R3.dst=R4.src RIGHT OUTER JOIN R5 ON R4.dst=R5.src;")
NAMES+=("agg_count_INNER-INNER-RIGHT")
QUERIES+=("SELECT R.src AS v1, COUNT(*) AS cnt FROM R INNER JOIN S ON R.dst=S.src INNER JOIN T ON S.dst=T.src RIGHT OUTER JOIN K ON T.dst=K.src GROUP BY R.src;")
NAMES+=("agg_count_LEFT-LEFT-FULL")
QUERIES+=("SELECT R.src AS v1, COUNT(*) AS cnt FROM R LEFT OUTER JOIN S ON R.dst=S.src LEFT OUTER JOIN T ON S.dst=T.src FULL OUTER JOIN K ON T.dst=K.src GROUP BY R.src;")
NAMES+=("agg_sum_INNER-INNER-RIGHT")
QUERIES+=("SELECT R.src AS v1, sum(K.dst) AS total FROM R INNER JOIN S ON R.dst=S.src INNER JOIN T ON S.dst=T.src RIGHT OUTER JOIN K ON T.dst=K.src GROUP BY R.src;")
NAMES+=("agg_sum_LEFT-LEFT-FULL")
QUERIES+=("SELECT R.src AS v1, sum(K.dst) AS total FROM R LEFT OUTER JOIN S ON R.dst=S.src LEFT OUTER JOIN T ON S.dst=T.src FULL OUTER JOIN K ON T.dst=K.src GROUP BY R.src;")

echo "Tracing ${#NAMES[@]} known-failing queries into $OUTDIR ..."
for i in "${!NAMES[@]}"; do
    echo "[$((i+1))/${#NAMES[@]}] ${NAMES[$i]}"
    trace_one "${QUERIES[$i]}" "$OUTDIR/${NAMES[$i]}.trace.txt"
done
echo "============================================================"
echo "Done. Trace files:"
ls -1 "$OUTDIR"/*.trace.txt