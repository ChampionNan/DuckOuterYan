#!/usr/bin/env bash
# ============================================================================
# experiment_semijoin.sh  —  Experiment 1: OuterYan SJ filters vs DuckDB SEMI.
# Spec: test/optimizer/outer_yan/EXPERIMENT_SEMIJOIN_DESIGN.md
#
# Fairness principle (§2): every mode runs the SAME `dim ⟕ fact` skeleton; only
# the reduction of `fact` differs:
#   BASELINE    outer_yan off            no reduction (plain LEFT join)  [floor]
#   BITMAP      outer_yan on, bitmap     SJ_BUILD+SJ_PROBE, KeyBitmap
#   HASH        outer_yan on, no bitmap  SJ_BUILD+SJ_PROBE, HashFilter
#   DUCKDB_SEMI outer_yan off            dim ⟕ (fact WHERE EXISTS dim)  → HASH_JOIN[SEMI]
#
# CORRECTNESS FIRST: before any timing, every selectivity point gates on
#   (a) oy_equiv_check(dim ⟕ fact)  — OuterYan ON==OFF (BITMAP/HASH vs BASELINE)
#   (b) oy_equiv_two(SEMI-rewrite vs plain) — the EXISTS form == the plain join
# A point that fails the gate is reported and NOT timed.
#
# Selectivity sweep (§3.1): `fact` has N rows over key domain DOM; `dim` holds a
# fraction p∈{0,.1,…,1} of the domain, so the reduction keeps ≈p·N of fact.
#
# NOTE: DEBUG-build timings are directional only; use --bin <release duckdb> for
# headline numbers (the design targets a release build).
#
# USAGE: experiment_semijoin.sh [options]
#   -b,--bin PATH    duckdb (default build/debug/duckdb)
#   -N,--n N         fact row count     (default 100000)
#   -D,--dom N       key domain size    (default 20000)
#   -n,--runs N      timed runs         (default 5)
#   -t,--timeout S   per-query timeout  (default 120)
#      --tpch SF     also run the TPC-H end-to-end family at scale factor SF
# ============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export DUCKDB_BIN="${DUCKDB_BIN:-$REPO_ROOT/build/debug/duckdb}"

N=100000; DOM=20000; RUNS=5; TPCH=""; OUT=""
export OY_MIN_SECS=5; export OY_TIMEOUT_SECS=300
while [ $# -gt 0 ]; do case "$1" in
    -b|--bin) DUCKDB_BIN="$2"; shift 2;;
    -N|--n) N="$2"; shift 2;;
    -D|--dom) DOM="$2"; shift 2;;
    -n|--runs) RUNS="$2"; shift 2;;
    --min-secs) export OY_MIN_SECS="$2"; shift 2;;
    -t|--timeout) export OY_TIMEOUT_SECS="$2"; shift 2;;
    --tpch) TPCH="$2"; shift 2;;
    -o|--out) OUT="$2"; shift 2;;
    -h|--help) sed -n '2,/^set /{/^set /q;p}' "${BASH_SOURCE[0]}"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 2;; esac; done
OUT="${OUT:-$REPO_ROOT/experiment_semijoin_results.txt}"

[ -x "$DUCKDB_BIN" ] || { echo "Error: duckdb not executable: $DUCKDB_BIN" >&2; exit 1; }
source "$SCRIPT_DIR/outer_yan_bench_lib.sh"

# Config preludes (each mode = one SET string). The bitmap budget is a session
# VARIABLE (SET VARIABLE …), read by PhysicalSJBuild::GetBitmapBudget: a large
# budget allows KeyBitmap; 0 forces HashFilter.
SET_OFF="SET disabled_optimizers TO 'outer_yan';"
SET_BMP="SET disabled_optimizers TO ''; SET VARIABLE outer_yan_bitmap_max_bytes=16777216;"
SET_HASH="SET disabled_optimizers TO ''; SET VARIABLE outer_yan_bitmap_max_bytes=0;"

DB="$(mktemp -u).duckdb"
trap 'rm -f "$DB" "$DB".wal' EXIT
echo "Building fact: N=$N rows, key domain DOM=$DOM ..."
"$DUCKDB_BIN" "$DB" >/dev/null <<SQL
CREATE TABLE fact AS SELECT i AS fid, (i % $DOM) AS fk, i AS fv FROM range($N) t(i);
SQL

# Probe: does this binary accept the bitmap-budget variable? (If not, BITMAP and
# HASH collapse to the same default OuterYan run — reported, not faked.)
if ! "$DUCKDB_BIN" "$DB" -c "SET VARIABLE outer_yan_bitmap_max_bytes=0;" >/dev/null 2>&1; then
    echo "WARNING: 'SET VARIABLE outer_yan_bitmap_max_bytes' not accepted —"
    echo "         BITMAP and HASH modes will both use default OuterYan settings."
fi

JOIN="SELECT * FROM dim LEFT OUTER JOIN fact ON dim.k=fact.fk;"
SEMI="SELECT * FROM dim LEFT OUTER JOIN (SELECT * FROM fact f WHERE EXISTS (SELECT 1 FROM dim d2 WHERE f.fk=d2.k)) fr ON dim.k=fr.fk;"

{   # whole report teed to $OUT
echo "# OuterYan semi-join experiment   $(date '+%F %T')"
echo "# bin=$DUCKDB_BIN  N=$N  DOM=$DOM  runs=$RUNS"
echo
echo "================= Selectivity sweep (dim ⟕ fact) ================="
printf '%-5s %-8s %-4s %9s %9s %9s %9s %8s %8s\n' \
       p dimKeys sj Base Bmp Hash Semi SpBmp SpHash
echo "----------------------------------------------------------------------------------"

for p in 0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0; do
    DIMK="$(awk -v p="$p" -v d="$DOM" 'BEGIN{printf "%d", p*d}')"
    "$DUCKDB_BIN" "$DB" >/dev/null 2>&1 <<SQL
CREATE OR REPLACE TABLE dim AS SELECT i AS k, i AS v FROM range($DIMK) t(i);
SQL
    # ---- correctness gate (silent unless it fails) ----
    g1="$(oy_equiv_check "$DB" "p=$p dim⟕fact ON==OFF" "$JOIN")"; r1=$?
    g2="$(oy_equiv_two   "$DB" "p=$p SEMI==plain" "$SET_OFF" "$SEMI" "$JOIN")"; r2=$?
    if [ $r1 -ne 0 ] || [ $r2 -ne 0 ]; then
        echo "$g1"; echo "$g2"
        printf '%-5s %-8s %-4s %9s %9s %9s %9s %8s %8s\n' "$p" "$DIMK" "GATE-FAIL" - - - - - -
        continue
    fi
    # ---- SJ inserted? ----
    if { echo "$SET_BMP"; echo "EXPLAIN (FORMAT json) ${JOIN%;};"; } \
         | "$DUCKDB_BIN" "$DB" -list -noheader 2>/dev/null | grep -q 'SJ_PROBE'; then sj="yes"; else sj="no"; fi
    # ---- timing (oy_time_min prints "min iters window"; take the min) ----
    base="$(oy_time_min "$DB" "$SET_OFF"  "$JOIN" "$RUNS" 1)"; base="${base%% *}"
    bmp="$(oy_time_min  "$DB" "$SET_BMP"  "$JOIN" "$RUNS" 1)"; bmp="${bmp%% *}"
    hash="$(oy_time_min "$DB" "$SET_HASH" "$JOIN" "$RUNS" 1)"; hash="${hash%% *}"
    semi="$(oy_time_min "$DB" "$SET_OFF"  "$SEMI" "$RUNS" 1)"; semi="${semi%% *}"
    spb="$(awk -v a="$base" -v b="$bmp"  'BEGIN{print (b+0>0? sprintf("%.2f",a/b):"NA")}')"
    sph="$(awk -v a="$base" -v b="$hash" 'BEGIN{print (b+0>0? sprintf("%.2f",a/b):"NA")}')"
    printf '%-5s %-8s %-4s %9s %9s %9s %9s %8s %8s\n' "$p" "$DIMK" "$sj" "$base" "$bmp" "$hash" "$semi" "$spb" "$sph"
done
echo "----------------------------------------------------------------------------------"
echo "SpBmp/SpHash = Base/mode (>1 = reduction beats the plain join). sj=no => OuterYan"
echo "did not insert a semi-join for this skeleton (BITMAP/HASH then equal BASELINE)."

# --- End-to-end TPC-H family (optional) -------------------------------------
if [ -n "$TPCH" ]; then
    echo
    echo "================= End-to-end TPC-H (sf=$TPCH) ================="
    if ! "$DUCKDB_BIN" -c "CALL dbgen(sf=0);" >/dev/null 2>&1; then
        echo "tpch extension not available in $DUCKDB_BIN — skipping."
    else
        "$DUCKDB_BIN" "$DB" -c "CALL dbgen(sf=$TPCH);" >/dev/null 2>&1
        printf '%-7s %9s %9s %9s %8s %8s\n' query Base Bmp Hash SpBmp SpHash
        echo "------------------------------------------------------------"
        th() {  # $1=label $2=query
            local g; g="$(oy_equiv_check "$DB" "$1" "$2")"
            case "$g" in *"equiv OK"*) :;; *) echo "$g"; printf '%-7s %9s\n' "$1" "GATE-FAIL"; return;; esac
            local base bmp hash spb sph
            base="$(oy_time_min "$DB" "$SET_OFF"  "$2" "$RUNS" 1)"; base="${base%% *}"
            bmp="$(oy_time_min  "$DB" "$SET_BMP"  "$2" "$RUNS" 1)"; bmp="${bmp%% *}"
            hash="$(oy_time_min "$DB" "$SET_HASH" "$2" "$RUNS" 1)"; hash="${hash%% *}"
            spb="$(awk -v a="$base" -v b="$bmp"  'BEGIN{print (b+0>0? sprintf("%.2f",a/b):"NA")}')"
            sph="$(awk -v a="$base" -v b="$hash" 'BEGIN{print (b+0>0? sprintf("%.2f",a/b):"NA")}')"
            printf '%-7s %9s %9s %9s %8s %8s\n' "$1" "$base" "$bmp" "$hash" "$spb" "$sph"
        }
        th TH-S1 "SELECT * FROM customer LEFT OUTER JOIN orders ON c_custkey=o_custkey LEFT OUTER JOIN lineitem ON o_orderkey=l_orderkey;"
        th TH-S2 "SELECT * FROM nation LEFT OUTER JOIN supplier ON n_nationkey=s_nationkey LEFT OUTER JOIN lineitem ON s_suppkey=l_suppkey;"
        th TH-S3 "SELECT * FROM region LEFT OUTER JOIN nation ON r_regionkey=n_regionkey RIGHT OUTER JOIN supplier ON n_nationkey=s_nationkey INNER JOIN customer ON s_nationkey=c_nationkey;"
        th TH-S4 "SELECT * FROM part LEFT OUTER JOIN partsupp ON p_partkey=ps_partkey LEFT OUTER JOIN supplier ON ps_suppkey=s_suppkey LEFT OUTER JOIN nation ON s_nationkey=n_nationkey;"
    fi
fi
} | tee "$OUT"
echo "Results written to $OUT"
