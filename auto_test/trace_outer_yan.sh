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
# Data + loading mirror the graph DB used by experiment_onoff.sh (R1..R10 +
# R/S/T/K views), so a query that FAILs there can be traced here byte-for-byte.
#
# USAGE:
#   trace_outer_yan.sh fails                 # trace all 5 known-failing queries
#   trace_outer_yan.sh -q "SELECT ... ;"     # trace one ad-hoc query
#   trace_outer_yan.sh -q "..." -o out.txt   # choose the output file
#   options: -b/--bin PATH   duckdb binary (default build/debug/duckdb)
#            -d/--outdir DIR  trace dir for `fails` mode (default ./oy_traces)
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$REPO_ROOT/test/sql/optimizer/outer_yan/data"
DUCKDB_BIN="${DUCKDB_BIN:-$REPO_ROOT/build/debug/duckdb}"
OUTDIR="$SCRIPT_DIR/results/oy_traces"
MODE=""
QUERY=""
OUTFILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        fails)         MODE="fails"; shift ;;
        -q|--query)    MODE="one"; QUERY="$2"; shift 2 ;;
        -o|--out)      OUTFILE="$2"; shift 2 ;;
        -b|--bin)      DUCKDB_BIN="$2"; shift 2 ;;
        -d|--outdir)   OUTDIR="$2"; shift 2 ;;
        -h|--help)     sed -n '2,/^set /{/^set /q;p}' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
[ -n "$MODE" ] || { echo "Nothing to do; pass 'fails' or -q \"SQL\". See --help." >&2; exit 2; }
[ -x "$DUCKDB_BIN" ] || { echo "Error: duckdb binary not found: $DUCKDB_BIN" >&2; exit 1; }

# --- build the database once (same recipe as the experiment_onoff graph DB) ----
shopt -s nullglob
CSVS=("$DATA_DIR"/R*.csv)
shopt -u nullglob
[ ${#CSVS[@]} -gt 0 ] || { echo "Error: no R*.csv under $DATA_DIR" >&2; exit 1; }

DB_FILE="$(mktemp -u).duckdb"
trap 'rm -f "$DB_FILE" "$DB_FILE".wal' EXIT
{
    for csv in "${CSVS[@]}"; do
        t="$(basename "$csv" .csv)"
        echo "CREATE TABLE $t AS SELECT * FROM read_csv('$csv', header=false, columns={'src':'BIGINT','dst':'BIGINT'});"
    done
    echo "CREATE VIEW R AS SELECT * FROM R1;"
    echo "CREATE VIEW S AS SELECT * FROM R2;"
    echo "CREATE VIEW T AS SELECT * FROM R3;"
    echo "CREATE VIEW K AS SELECT * FROM R4;"
} | "$DUCKDB_BIN" "$DB_FILE" >/dev/null || { echo "Error: failed to load data" >&2; exit 1; }

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
