#!/usr/bin/env bash
# ============================================================================
# experiment_semijoin.sh  —  Experiment 1: OuterYan SJ filters vs DuckDB SEMI.
# Spec: test/optimizer/outer_yan/EXPERIMENT_SEMIJOIN_DESIGN.md
#
# A small dimension reduces a large fact through the join, so OuterYan can insert
# a semi-join / bloom filter (SJ_BUILD + SJ_PROBE). Each query is timed under:
#   BASELINE    outer_yan off            no reduction (plain join)        [floor]
#   BITMAP      outer_yan on, bitmap     SJ_BUILD+SJ_PROBE, KeyBitmap
#   HASH        outer_yan on, no bitmap  SJ_BUILD+SJ_PROBE, HashFilter
#   DUCKDB_SEMI outer_yan off            EXISTS-rewrite → HASH_JOIN[SEMI]  (sweep only)
#
# Star schema (built here): fact(fid,fk1,fk2,fk3,fv) over key domain DOM +
# dims d1,d2,d3(k,v) holding a fraction p of the domain (the reduction selectivity).
#
# Section A — CORPUS: every query in outerjoin_query/semijoin/ (54 shapes ×
#   join-type vectors), gated on ON==OFF, then timed BASELINE/BITMAP/HASH.
# Section B — SWEEP: the dim⟕fact skeleton across selectivity p∈{0..1}, all 4 modes.
#
# USAGE: experiment_semijoin.sh [options]
#   -b,--bin PATH    duckdb (default build/release/duckdb, else build/debug)
#   -N,--n N         fact row count           (default 100000)
#   -D,--dom N       key domain size          (default 20000)
#   -p,--sel P       dim selectivity for Sec A (default 0.5 → dims hold p·DOM keys)
#   -n,--runs N      timed runs (floor)       (default 5)
#      --min-secs S  timing window/query      (default 5)
#   -t,--timeout S   soft per-query timeout   (default 120)
#      --kill-after S hard SIGKILL any duckdb query > S sec (default 300; 0=off)
#      --tpch SF     also run the TPC-H end-to-end family at scale factor SF
#   -o,--out FILE    results (default experiment_semijoin_results.txt)
# ============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export DUCKDB_BIN="${DUCKDB_BIN:-$REPO_ROOT/build/release/duckdb}"
[ -x "$DUCKDB_BIN" ] || export DUCKDB_BIN="$REPO_ROOT/build/debug/duckdb"
SJ_DIR="$SCRIPT_DIR/outerjoin_query/semijoin"

N=100000; DOM=20000; SEL=0.5; RUNS=5; TPCH=""; OUT=""; KILL_AFTER=300
export OY_MIN_SECS=5; export OY_TIMEOUT_SECS=120
while [ $# -gt 0 ]; do case "$1" in
    -b|--bin) export DUCKDB_BIN="$2"; shift 2;;
    -N|--n) N="$2"; shift 2;;
    -D|--dom) DOM="$2"; shift 2;;
    -p|--sel) SEL="$2"; shift 2;;
    -n|--runs) RUNS="$2"; shift 2;;
    --min-secs) export OY_MIN_SECS="$2"; shift 2;;
    -t|--timeout) export OY_TIMEOUT_SECS="$2"; shift 2;;
    --kill-after) KILL_AFTER="$2"; shift 2;;
    --tpch) TPCH="$2"; shift 2;;
    -o|--out) OUT="$2"; shift 2;;
    -h|--help) sed -n '2,/^set /p' "${BASH_SOURCE[0]}"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 2;; esac; done
OUT="${OUT:-$REPO_ROOT/experiment_semijoin_results.txt}"

[ -x "$DUCKDB_BIN" ] || { echo "Error: duckdb not executable: $DUCKDB_BIN" >&2; exit 1; }
source "$SCRIPT_DIR/outer_yan_bench_lib.sh"

# --- hard watchdog: SIGKILL any of our duckdb queries running > KILL_AFTER secs -
_oy_watchdog() {  # $1=binary  $2=max-secs
    local pid e d rest p1 p2 p3 h m s sec
    while true; do
        for pid in $(pgrep -f "$1" 2>/dev/null); do
            e="$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')"; [ -z "$e" ] && continue
            d=0; rest="$e"; case "$e" in *-*) d="${e%%-*}"; rest="${e#*-}";; esac
            IFS=: read -r p1 p2 p3 <<< "$rest"
            if [ -n "$p3" ]; then h=$p1; m=$p2; s=$p3; else h=0; m=$p1; s=$p2; fi
            sec=$((10#${d:-0}*86400 + 10#${h:-0}*3600 + 10#${m:-0}*60 + 10#${s:-0}))
            [ "$sec" -gt "$2" ] && kill -9 "$pid" 2>/dev/null \
                && echo "  [watchdog] SIGKILL $(basename "$1") pid=$pid etime=$e (>$2s)" >&2
        done
        sleep 15
    done
}
WATCHDOG_PID=""
DB="$(mktemp -u).duckdb"
trap 'rm -f "$DB" "$DB".wal; [ -n "$WATCHDOG_PID" ] && kill "$WATCHDOG_PID" 2>/dev/null' EXIT
if [ "${KILL_AFTER:-0}" -gt 0 ] 2>/dev/null; then
    _oy_watchdog "$DUCKDB_BIN" "$KILL_AFTER" & WATCHDOG_PID=$!
fi

# Config preludes. Bitmap budget is a session VARIABLE read by PhysicalSJBuild:
# large budget allows KeyBitmap; 0 forces HashFilter.
SET_OFF="SET disabled_optimizers TO 'outer_yan';"
SET_BMP="SET disabled_optimizers TO ''; SET VARIABLE outer_yan_bitmap_max_bytes=16777216;"
SET_HASH="SET disabled_optimizers TO ''; SET VARIABLE outer_yan_bitmap_max_bytes=0;"

# --- build the star schema (fact + d1,d2,d3 at selectivity SEL) --------------
DIMK="$(awk -v p="$SEL" -v d="$DOM" 'BEGIN{printf "%d", (p*d<1?1:p*d)}')"
echo "Building star schema: fact N=$N (domain DOM=$DOM, 3 FKs), d1/d2/d3 = $DIMK keys (p=$SEL) ..." >&2
"$DUCKDB_BIN" "$DB" >/dev/null <<SQL || { echo "schema build failed" >&2; exit 1; }
CREATE TABLE fact AS SELECT i AS fid, (i % $DOM) AS fk1, ((i*7+1) % $DOM) AS fk2,
                            ((i*13+3) % $DOM) AS fk3, i AS fv FROM range($N) t(i);
CREATE TABLE d1 AS SELECT i AS k, i AS v FROM range($DIMK) t(i);
CREATE TABLE d2 AS SELECT i AS k, i*2 AS v FROM range($DIMK) t(i);
CREATE TABLE d3 AS SELECT i AS k, i*3 AS v FROM range($DIMK) t(i);
SQL
if ! "$DUCKDB_BIN" "$DB" -c "SET VARIABLE outer_yan_bitmap_max_bytes=0;" >/dev/null 2>&1; then
    echo "WARNING: 'SET VARIABLE outer_yan_bitmap_max_bytes' not accepted — BITMAP and HASH collapse." >&2
fi

# collect corpus queries (skeleton_* excluded; they drive the sweep)
LABELS=(); SQLS=()
for f in "$SJ_DIR"/*.sql; do
    b="$(basename "$f" .sql)"; case "$b" in skeleton_*) continue;; esac
    LABELS+=("$b"); SQLS+=("$(cat "$f")")
done

{   # whole report teed to $OUT
echo "# OuterYan semi-join experiment   $(date '+%F %T')"
echo "# bin=$DUCKDB_BIN  fact N=$N  DOM=$DOM  dims=$DIMK (p=$SEL)  runs=$RUNS  corpus=${#LABELS[@]}"
echo

# ---- Section A: corpus (BASELINE vs BITMAP vs HASH, gated on ON==OFF) -------
echo "===================== A. semi-join corpus (${#LABELS[@]} queries) ====================="
printf '%-26s %-3s %9s %9s %9s %8s %8s %-8s\n' query sj Base Bmp Hash SpBmp SpHash correct
echo "--------------------------------------------------------------------------------------"
NSJ=0; NTIMED=0; SUMB=0; NB=0; SUMH=0; NH=0
for ((i=0; i<${#LABELS[@]}; i++)); do
    id="${LABELS[i]}"; q="${SQLS[i]}"
    g="$(oy_equiv_check "$DB" "$id" "$q")"
    case "$g" in *"equiv OK"*) ok="OK";; *"NOT EQUIV"*) ok="NOTEQ";; *"TIMEOUT"*) ok="TMO";; *) ok="ERR";; esac
    if [ "$ok" != "OK" ]; then
        printf '%-26s %-3s %9s %9s %9s %8s %8s %-8s\n' "$id" "-" - - - - - "$ok"; continue
    fi
    if { echo "$SET_BMP"; echo "EXPLAIN (FORMAT json) ${q%;};"; } \
         | "$DUCKDB_BIN" "$DB" -list -noheader 2>/dev/null | grep -q 'SJ_PROBE'; then sj="yes"; NSJ=$((NSJ+1)); else sj="no"; fi
    base="$(oy_time_min "$DB" "$SET_OFF"  "$q" "$RUNS" 1)"; base="${base%% *}"
    bmp="$(oy_time_min  "$DB" "$SET_BMP"  "$q" "$RUNS" 1)"; bmp="${bmp%% *}"
    hash="$(oy_time_min "$DB" "$SET_HASH" "$q" "$RUNS" 1)"; hash="${hash%% *}"
    spb="$(awk -v a="$base" -v b="$bmp"  'BEGIN{print (a!="NA"&&b+0>0? sprintf("%.2f",a/b):"NA")}')"
    sph="$(awk -v a="$base" -v b="$hash" 'BEGIN{print (a!="NA"&&b+0>0? sprintf("%.2f",a/b):"NA")}')"
    printf '%-26s %-3s %9s %9s %9s %8s %8s %-8s\n' "$id" "$sj" "$base" "$bmp" "$hash" "$spb" "$sph" "OK"
    NTIMED=$((NTIMED+1))
    [ "$spb" != "NA" ] && { SUMB="$(awk -v s="$SUMB" -v r="$spb" 'BEGIN{print s+r}')"; NB=$((NB+1)); }
    [ "$sph" != "NA" ] && { SUMH="$(awk -v s="$SUMH" -v r="$sph" 'BEGIN{print s+r}')"; NH=$((NH+1)); }
    printf '  [%3d/%d] %-26s %s sj=%s\n' "$((i+1))" "${#LABELS[@]}" "$id" "$ok" "$sj" >&2
done
echo "--------------------------------------------------------------------------------------"
MB="$(awk -v s="$SUMB" -v n="$NB" 'BEGIN{print (n? sprintf("%.2f",s/n):"-")}')"
MH="$(awk -v s="$SUMH" -v n="$NH" 'BEGIN{print (n? sprintf("%.2f",s/n):"-")}')"
echo "corpus=${#LABELS[@]}  timed=$NTIMED  SJ-inserted=$NSJ   mean SpBmp=$MB  mean SpHash=$MH"
echo "Sp>1 = OuterYan reduction beats the plain join. sj=no => no SJ inserted (Bmp/Hash≈Base)."

# ---- Section B: selectivity sweep on the dim⟕fact skeleton -----------------
JOIN="$(cat "$SJ_DIR/skeleton_join.sql")"
SEMI="$(cat "$SJ_DIR/skeleton_semi.sql")"
echo
echo "===================== B. selectivity sweep (d1 ⟕ fact) ====================="
printf '%-5s %-8s %-4s %9s %9s %9s %9s %8s %8s\n' p dimKeys sj Base Bmp Hash Semi SpBmp SpHash
echo "----------------------------------------------------------------------------------"
for p in 0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0; do
    DK="$(awk -v p="$p" -v d="$DOM" 'BEGIN{printf "%d", p*d}')"
    "$DUCKDB_BIN" "$DB" >/dev/null 2>&1 <<SQL
CREATE OR REPLACE TABLE d1 AS SELECT i AS k, i AS v FROM range($DK) t(i);
SQL
    g1="$(oy_equiv_check "$DB" "p=$p ON==OFF" "$JOIN")"; r1=$?
    g2="$(oy_equiv_two   "$DB" "p=$p SEMI==plain" "$SET_OFF" "$SEMI" "$JOIN")"; r2=$?
    if [ $r1 -ne 0 ] || [ $r2 -ne 0 ]; then
        printf '%-5s %-8s %-4s %9s %9s %9s %9s %8s %8s\n' "$p" "$DK" "GATEFAIL" - - - - - -; continue
    fi
    if { echo "$SET_BMP"; echo "EXPLAIN (FORMAT json) ${JOIN%;};"; } \
         | "$DUCKDB_BIN" "$DB" -list -noheader 2>/dev/null | grep -q 'SJ_PROBE'; then sj="yes"; else sj="no"; fi
    base="$(oy_time_min "$DB" "$SET_OFF"  "$JOIN" "$RUNS" 1)"; base="${base%% *}"
    bmp="$(oy_time_min  "$DB" "$SET_BMP"  "$JOIN" "$RUNS" 1)"; bmp="${bmp%% *}"
    hash="$(oy_time_min "$DB" "$SET_HASH" "$JOIN" "$RUNS" 1)"; hash="${hash%% *}"
    semi="$(oy_time_min "$DB" "$SET_OFF"  "$SEMI" "$RUNS" 1)"; semi="${semi%% *}"
    spb="$(awk -v a="$base" -v b="$bmp"  'BEGIN{print (b+0>0? sprintf("%.2f",a/b):"NA")}')"
    sph="$(awk -v a="$base" -v b="$hash" 'BEGIN{print (b+0>0? sprintf("%.2f",a/b):"NA")}')"
    printf '%-5s %-8s %-4s %9s %9s %9s %9s %8s %8s\n' "$p" "$DK" "$sj" "$base" "$bmp" "$hash" "$semi" "$spb" "$sph"
done
echo "----------------------------------------------------------------------------------"

# --- End-to-end TPC-H family (optional) -------------------------------------
if [ -n "$TPCH" ]; then
    echo
    echo "===================== C. End-to-end TPC-H (sf=$TPCH) ====================="
    if ! "$DUCKDB_BIN" -c "CALL dbgen(sf=0.01);" >/dev/null 2>&1; then
        echo "tpch extension not available in $DUCKDB_BIN — skipping."
    else
        "$DUCKDB_BIN" "$DB" -c "CALL dbgen(sf=$TPCH);" >/dev/null 2>&1
        printf '%-32s %9s %9s %9s %8s %8s\n' query Base Bmp Hash SpBmp SpHash
        echo "--------------------------------------------------------------------------"
        for tf in "$SCRIPT_DIR"/outerjoin_query/tpch/*.sql; do
            case "$tf" in *_off.sql) continue;; esac
            id="$(basename "$tf" .sql)"; q="$(cat "$tf")"
            g="$(oy_equiv_check "$DB" "$id" "$q")"; case "$g" in *"equiv OK"*) :;; *) printf '%-32s %9s\n' "$id" "GATE-FAIL"; continue;; esac
            base="$(oy_time_min "$DB" "$SET_OFF"  "$q" "$RUNS" 1)"; base="${base%% *}"
            bmp="$(oy_time_min  "$DB" "$SET_BMP"  "$q" "$RUNS" 1)"; bmp="${bmp%% *}"
            hash="$(oy_time_min "$DB" "$SET_HASH" "$q" "$RUNS" 1)"; hash="${hash%% *}"
            spb="$(awk -v a="$base" -v b="$bmp"  'BEGIN{print (a!="NA"&&b+0>0? sprintf("%.2f",a/b):"NA")}')"
            sph="$(awk -v a="$base" -v b="$hash" 'BEGIN{print (a!="NA"&&b+0>0? sprintf("%.2f",a/b):"NA")}')"
            printf '%-32s %9s %9s %9s %8s %8s\n' "$id" "$base" "$bmp" "$hash" "$spb" "$sph"
        done
    fi
fi
} | tee "$OUT"
echo "Results written to $OUT"
