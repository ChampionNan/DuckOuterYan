#!/usr/bin/env bash
# ============================================================================
# experiment_onoff.sh  —  OuterYan ON-vs-OFF correctness + performance test.
#
# Per corpus query, IN THIS ORDER:
#   1. CORRECTNESS GATE — oy_equiv_check (ON==OFF on the bare query). A query that
#      is not equivalence-preserving (or crashes/times out) is NOT timed.
#   2. JOIN_REORDER — oy_regime: No (OuterYan keeps DuckDB's join order) vs
#      Yes (OuterYan reorders), from the join-order signature.
#   3. TIMING — oy_time_median off vs on (threads=1 + OY_THREADS, median of 10 runs).
#
# USAGE: experiment_onoff.sh [options]
#   -b,--bin PATH     duckdb (default build/release/duckdb, else build/debug)
#   -n,--runs N       timed iterations per config (default 10; median taken)
#   -t,--timeout S    per-query timeout sec (default 300; via `timeout`)
#      --only select|agg|pred|tpch|tpcds|job|graph|bench|all  query families
#                     (default all); bench = tpch+tpcds+job
#      --pattern GLOB  only queries whose label matches (default *)
#      --exclude GLOB  skip labels matching any '|'-separated glob
#      --limit N       cap number of queries (0 = no cap, default 0)
#   -o,--out FILE     results file (default experiment_onoff_<timestamp>.txt)
# ============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Unified config: defines DUCKDB_BIN, GRAPH_DATASET, TPCH_SF/TPCDS_SF,
# OY_TIMEOUT_SECS, OY_RUNS.
. "$SCRIPT_DIR/configs.sh"
[ -x "$DUCKDB_BIN" ] || export DUCKDB_BIN="$REPO_ROOT/build/debug/duckdb"
CORPUS="${OY_CORPUS:-$SCRIPT_DIR/outerjoin_query}"

RUNS="${OY_RUNS:-3}"; ONLY="all"; PATTERN="*"; EXCLUDE=""; LIMIT=0; OUT=""
while [ $# -gt 0 ]; do case "$1" in
    -b|--bin) export DUCKDB_BIN="$2"; shift 2;;
    -n|--runs) RUNS="$2"; shift 2;;
    -t|--timeout) export OY_TIMEOUT_SECS="$2"; shift 2;;
    --only) ONLY="$2"; shift 2;;
    --pattern) PATTERN="$2"; shift 2;;
    --exclude) EXCLUDE="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    -o|--out) OUT="$2"; shift 2;;
    -h|--help) sed -n '2,/^set /p' "${BASH_SOURCE[0]}"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 2;; esac; done
_default_out="$SCRIPT_DIR/results/experiment_onoff_$(date +%Y%m%d_%H%M%S).txt"
OUT="${OUT:-$_default_out}"
mkdir -p "$(dirname "$OUT")"

[ -x "$DUCKDB_BIN" ] || { echo "Error: duckdb not executable: $DUCKDB_BIN" >&2; exit 1; }
case "$DUCKDB_BIN" in *debug*) echo "WARNING: timing a DEBUG build — directional only; pass --bin <release>." >&2;; esac

# ============================================================================
# BENCH LIBRARY (inlined from outer_yan_bench_lib.sh)
# ============================================================================
OY_OFF="SET disabled_optimizers TO 'outer_yan';"
OY_ON="SET disabled_optimizers TO '';"
: "${OY_TIMEOUT_SECS:=300}"
OY_TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
[ "${OY_TIMEOUT_SECS}" = "0" ] && OY_TIMEOUT_BIN=""

# Invoke duckdb optionally under timeout.
oy_duck() {
    if [ -n "$OY_TIMEOUT_BIN" ]; then
        "$OY_TIMEOUT_BIN" "$OY_TIMEOUT_SECS" "$DUCKDB_BIN" "$@"
    else
        "$DUCKDB_BIN" "$@"
    fi
}

# --- the correctness atom ---------------------------------------------------
# Runs the SAME query with OuterYan OFF and ON against <db>, compares both
# result sets (multiset + order-independent) via ORDER BY ALL inside DuckDB.
# RETURNS: 0 PASS | 1 FAIL (rows differ) | 2 ERROR | 3 TIMEOUT.
oy_equiv_check() {
    local db="$1" label="$2" query="$3"
    local off on eoff eon roff ron rc=0
    off=$(mktemp); on=$(mktemp); eoff=$(mktemp); eon=$(mktemp)

    local sorted_q="SELECT * FROM (${query%;}) _oy_sub ORDER BY ALL;"

    { echo "$OY_OFF"; echo "$sorted_q"; } \
        | oy_duck "$db" -csv -noheader 2>"$eoff" > "$off"; roff=${PIPESTATUS[1]}
    { echo "$OY_ON";  echo "$sorted_q"; } \
        | oy_duck "$db" -csv -noheader 2>"$eon"  > "$on";  ron=${PIPESTATUS[1]}

    if [ "${roff:-0}" -eq 124 ] || [ "${ron:-0}" -eq 124 ]; then
        echo "  TIMEOUT (${OY_TIMEOUT_SECS}s): $label"; rc=3
    elif grep -qE 'Error:' "$eoff"; then
        echo "  ERROR (off): $label"; grep -E 'Error:' "$eoff" | head -1 | sed 's/^/        /'; rc=2
    elif grep -qE 'Error:' "$eon"; then
        echo "  ERROR (on):  $label"; grep -E 'Error:' "$eon" | head -1 | sed 's/^/        /'; rc=2
    elif diff -q "$off" "$on" >/dev/null; then
        echo "  equiv OK: $label ($(wc -l < "$off" | tr -d ' ') rows)"; rc=0
    else
        echo "  NOT EQUIV: $label (off=$(wc -l < "$off" | tr -d ' ') on=$(wc -l < "$on" | tr -d ' '))"
        diff "$off" "$on" | head -6 | sed 's/^/        /'; rc=1
    fi
    rm -f "$off" "$on" "$eoff" "$eon"
    return $rc
}

# --- timing -----------------------------------------------------------------
# oy_time_median: run query K times (after 2 warm-up runs), return median time.
# Output: "median_time iteration_count"
: "${OY_RUNS:=10}"

oy_time_median() {
    local db="$1" set_sql="$2" query="$3" runs="$4" threads="$5"
    local script i
    script="PRAGMA threads=${threads};"$'\n'"${set_sql}"$'\n'
    # 2 warm-up runs (timer off)
    script+="${query%;};"$'\n'
    script+="${query%;};"$'\n'
    # timed runs
    script+=".timer on"$'\n'
    for ((i=0; i<runs; i++)); do script+="${query%;};"$'\n'; done
    local times
    times="$(printf '%s' "$script" | oy_duck "$db" -noheader 2>&1 \
        | awk '/Run Time/{for(i=1;i<=NF;i++) if($i=="real") print $(i+1)}')"
    [ -z "$times" ] && { echo "NA 0"; return; }
    # compute median using sort + awk
    echo "$times" | sort -n | awk -v K="$runs" '
        { a[NR]=$1 }
        END {
            if(NR==0){ printf "NA 0"; exit }
            mid=int((NR+1)/2)
            if(NR%2==1) med=a[mid]
            else med=(a[NR/2]+a[NR/2+1])/2
            printf "%.4f %d", med, NR
        }'
}

# --- join-order signature (regime classification) ---------------------------
read -r -d '' OY_SIG_PY <<'PY' || true
import json,sys
raw=sys.stdin.read()
i,j=raw.find('['),raw.rfind(']')
if i<0 or j<0: print("NOSIG"); sys.exit(0)
try: data=json.loads(raw[i:j+1])
except Exception: print("BADSIG"); sys.exit(0)
def tabs(n,acc):
    ei=n.get("extra_info") or {}
    for key in ("Table","Text"):
        v=ei.get(key)
        if isinstance(v,str) and v: acc.add(v); break
    for c in (n.get("children") or []): tabs(c,acc)
sigs=[]
def walk(n):
    nm=(n.get("name") or "").upper()
    kids=n.get("children") or []
    if "JOIN" in nm and "SJ_" not in nm:
        s=set()
        for c in kids: tabs(c,s)
        if s: sigs.append("{"+",".join(sorted(s))+"}")
    for c in kids: walk(c)
for r in (data if isinstance(data,list) else [data]): walk(r)
print("|".join(sorted(sigs)) if sigs else "NOJOIN")
PY

oy_sig() {
    { echo "$2"; echo "EXPLAIN (FORMAT json) ${3%;};"; } \
        | "$DUCKDB_BIN" "$1" -list -noheader 2>/dev/null | python3 -c "$OY_SIG_PY"
}

oy_regime() {
    local db="$1" query="$2" s_off s_on sj
    s_off="$(oy_sig "$db" "$OY_OFF" "$query")"
    s_on="$(oy_sig  "$db" "$OY_ON"  "$query")"
    if { echo "$OY_ON"; echo "EXPLAIN (FORMAT json) ${query%;};"; } \
        | "$DUCKDB_BIN" "$db" -list -noheader 2>/dev/null | grep -q 'SJ_PROBE'; then
        sj="yes"; else sj="no"; fi
    if [ "$s_off" = "$s_on" ]; then echo "No sj=$sj"; else echo "Yes sj=$sj"; fi
}

# ============================================================================
# FAMILIES — map --only to directories + per-family DB
# ============================================================================
case "$ONLY" in
    select) FAMS="graph";;          agg) FAMS="graph";;     pred) FAMS="graph";;
    tpch)   FAMS="tpch";;          tpcds) FAMS="tpcds";;   job) FAMS="job";;
    graph)  FAMS="graph";;
    bench) FAMS="tpch tpcds job";;
    all)    FAMS="graph tpch tpcds job";;
    *) echo "Unknown --only: $ONLY (select|agg|pred|tpch|tpcds|job|graph|bench|all)" >&2; exit 2;;
esac
need_graph=0; need_tpch=0; need_tpcds=0; need_job=0
for fam in $FAMS; do case "$fam" in
    graph) need_graph=1;; tpch) need_tpch=1;; tpcds) need_tpcds=1;;
    job) need_job=1;; esac; done

GRAPH_DB=""; TPCH_DB="$REPO_ROOT/tpch_db"; TPCDS_DB="$REPO_ROOT/tpcds_db"
JOB_DB="${JOB_DB:-$REPO_ROOT/job_db}"

# Delegate DB builds to build_db.sh
BUILD_DB="$SCRIPT_DIR/build_db.sh"

# graph DB: R1..R10 from SNAP graph data
if [ "$need_graph" = 1 ]; then
    GRAPH_DATASET="${GRAPH_DATASET:-bitcoin}"
    GRAPH_DATA_DIR="${GRAPH_DATA_DIR:-$REPO_ROOT/graph_data}"
    echo "Building graph R1..R10 from dataset=$GRAPH_DATASET ..." >&2
    # Build graph_db via build_db.sh (respects GRAPH_DATASET env)
    FORCE=1 bash "$BUILD_DB" graph 2>/dev/null || true
    if [ -f "$REPO_ROOT/graph_db" ]; then
        GRAPH_DB="$REPO_ROOT/graph_db"
    else
        echo "ERROR: graph_db not found. Run: bash auto_test/build_db.sh graph" >&2; exit 1
    fi
fi
# tpch / tpcds / job DBs: delegate to build_db.sh (builds only if missing)
if [ "$need_tpch" = 1 ] && [ ! -f "$TPCH_DB" ]; then
    bash "$BUILD_DB" tpch || { echo "WARNING: tpch build failed — skipping" >&2; need_tpch=0; }
fi
if [ "$need_tpcds" = 1 ] && [ ! -f "$TPCDS_DB" ]; then
    bash "$BUILD_DB" tpcds || { echo "WARNING: tpcds build failed — skipping" >&2; need_tpcds=0; }
fi
if [ "$need_job" = 1 ] && [ ! -f "$JOB_DB" ]; then
    SKIP_DOWNLOAD=0 bash "$BUILD_DB" job || { echo "WARNING: job build failed — skipping" >&2; need_job=0; }
fi

# ============================================================================
# COLLECT QUERIES — each tagged with its family DB
# ============================================================================
LABELS=(); SQLS=(); DBS=()
for fam in $FAMS; do
    case "$fam" in
        graph)  dir="$CORPUS/graph"; fdb="$GRAPH_DB";;
        tpch)   [ "$need_tpch"  = 1 ] || continue; dir="$CORPUS/tpch";  fdb="$TPCH_DB";;
        tpcds)  [ "$need_tpcds" = 1 ] || continue; dir="$CORPUS/tpcds"; fdb="$TPCDS_DB";;
        job)    [ "$need_job"   = 1 ] || continue; dir="$CORPUS/job";   fdb="$JOB_DB";;
    esac
    [ -d "$dir" ] || continue
    for f in "$dir"/*.sql; do
        case "$f" in *_off.sql) continue;; esac
        lbl="$(basename "$f" .sql)"
        case "$lbl" in $PATTERN) ;; *) continue;; esac
        if [ -n "$EXCLUDE" ]; then
            _skip=0; IFS='|' read -ra _ex <<< "$EXCLUDE"
            for _g in "${_ex[@]}"; do case "$lbl" in $_g) _skip=1; break;; esac; done
            [ "$_skip" = 1 ] && continue
        fi
        LABELS+=("$lbl"); SQLS+=("$(cat "$f")"); DBS+=("$fdb")
        [ "$LIMIT" -gt 0 ] && [ "${#LABELS[@]}" -ge "$LIMIT" ] && break
    done
    [ "$LIMIT" -gt 0 ] && [ "${#LABELS[@]}" -ge "$LIMIT" ] && break
done
[ "${#LABELS[@]}" -gt 0 ] || { echo "No corpus queries matched (only=$ONLY pattern=$PATTERN)" >&2; exit 1; }
SIZES="families=[$FAMS]  graph=$GRAPH_DATASET  tpch sf=$TPCH_SF  tpcds sf=$TPCDS_SF  job db=$JOB_DB"

# ============================================================================
# RUN: gate -> regime -> time, streaming results to $OUT and $CSV_OUT
# ============================================================================
CSV_OUT="${OUT%.txt}.csv"

# Header (truncate + write)
{
    echo "# OuterYan on/off experiment   $(date '+%F %T')"
    echo "# binary : $DUCKDB_BIN"
    echo "# corpus : $ONLY  (pattern=$PATTERN limit=$LIMIT) — ${#LABELS[@]} queries from $CORPUS"
    echo "# tables : $SIZES"
    echo "# timing : threads=1+${OY_THREADS}, median of ${RUNS} runs per config (2 warm-up + ${RUNS} timed)"
    echo "# correct: ON result multiset == OFF result; only correct queries are timed"
    echo
    echo "===================== LIVE PER-QUERY RESULTS =========================="
    echo "# Columns: T1 = single-thread, TM = multi-thread (threads=${OY_THREADS})"
    printf '%-34s %-5s %-9s %-10s %9s %9s %7s %9s %9s %7s\n' \
        query reord? correct note T1:off T1:on T1:spd TM:off TM:on TM:spd
    echo "----------------------------------------------------------------------"
} > "$OUT"

echo "query,reorder,correct,note,t1_off,t1_on,t1_speedup,tm_off,tm_on,tm_speedup,rows" > "$CSV_OUT"

QN=0; NSKIP=0; NTIMED=0; NNO=0; NYES=0; SUMNO=0; SUMYES=0
QLBL=(); QNREL=(); QCORRECT=(); QNOTE=(); QROWS=(); QREG=()
QDB=(); QSQL=()
QOFF1=(); QON1=(); QRATIO1=()
QOFFM=(); QONM=(); QRATIOM=()

# ==== Single pass: per query, correctness -> TM -> T1 (streamed to $OUT) ====
echo "--- Per-query: correctness + multi-thread (TM=${OY_THREADS}) + single-thread (T1=1) ---" >&2
for ((i=0; i<${#LABELS[@]}; i++)); do
    id="${LABELS[i]}"; sql="${SQLS[i]}"; db="${DBS[i]}"
    nrel="-"; case "$id" in *_N[0-9]*) nrel="$(printf '%s' "$id" | sed -nE 's/.*_N([0-9]+)_.*/\1/p')";; esac
    gate="$(oy_equiv_check "$db" "$id" "$sql")"
    case "$gate" in
        *"equiv OK"*)  correct="TRUE";  note="OK";        rows="$(printf '%s' "$gate" | grep -oE '[0-9]+ rows' | grep -oE '[0-9]+')";;
        *"NOT EQUIV"*) correct="FALSE"; note="NOT-EQUIV"; rows="$(printf '%s' "$gate" | grep -oE 'off=[0-9]+ on=[0-9]+')";;
        *"TIMEOUT"*)   correct="FALSE"; note="TIMEOUT";   rows="-";;
        *)             correct="FALSE"; note="ERROR";     rows="-";;
    esac
    reg="-"; offm="-"; onm="-"; ratiom="-"; off1="-"; on1="-"; ratio1="-"
    if [ "$correct" = "TRUE" ]; then
        reg="$(oy_regime "$db" "$sql")"; reg="${reg%% *}"
        local_rom="$(oy_time_median "$db" "$OY_OFF" "$sql" "$RUNS" "${OY_THREADS}")"
        local_rnm="$(oy_time_median "$db" "$OY_ON"  "$sql" "$RUNS" "${OY_THREADS}")"
        offm="$(echo "$local_rom" | awk '{print $1}')"; onm="$(echo "$local_rnm" | awk '{print $1}')"
        ratiom="$(awk -v off="$offm" -v on="$onm" 'BEGIN{ if(off!="NA"&&on!="NA"&&on+0>0) printf "%.3f", off/on; else print "NA" }')"
        local_ro1="$(oy_time_median "$db" "$OY_OFF" "$sql" "$RUNS" 1)"
        local_rn1="$(oy_time_median "$db" "$OY_ON"  "$sql" "$RUNS" 1)"
        off1="$(echo "$local_ro1" | awk '{print $1}')"; on1="$(echo "$local_rn1" | awk '{print $1}')"
        ratio1="$(awk -v off="$off1" -v on="$on1" 'BEGIN{ if(off!="NA"&&on!="NA"&&on+0>0) printf "%.3f", off/on; else print "NA" }')"
        NTIMED=$((NTIMED+1))
        if [ "$ratiom" != "NA" ]; then
            if [ "$reg" = "No" ]; then NNO=$((NNO+1));  SUMNO="$(awk -v s="$SUMNO" -v r="$ratiom" 'BEGIN{print s+r}')"
            else                       NYES=$((NYES+1)); SUMYES="$(awk -v s="$SUMYES" -v r="$ratiom" 'BEGIN{print s+r}')"; fi
        fi
    else
        NSKIP=$((NSKIP+1))
    fi
    QLBL[$QN]="$id"; QNREL[$QN]="$nrel"; QCORRECT[$QN]="$correct"; QNOTE[$QN]="$note"; QROWS[$QN]="$rows"
    QREG[$QN]="$reg"; QDB[$QN]="$db"; QSQL[$QN]="$sql"
    QOFFM[$QN]="$offm"; QONM[$QN]="$onm"; QRATIOM[$QN]="$ratiom"
    QOFF1[$QN]="$off1"; QON1[$QN]="$on1"; QRATIO1[$QN]="$ratio1"
    QN=$((QN+1))
    # ---- IMMEDIATE write to $OUT and $CSV_OUT ----
    printf '%-34s %-5s %-9s %-10s %9s %9s %7s %9s %9s %7s\n' \
        "$id" "$reg" "$correct" "$note" "$off1" "$on1" "$ratio1" "$offm" "$onm" "$ratiom" >> "$OUT"
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$id" "$reg" "$correct" "$note" "$off1" "$on1" "$ratio1" "$offm" "$onm" "$ratiom" "$rows" >> "$CSV_OUT"
    if [ "$correct" = "TRUE" ]; then
        printf '  [%3d/%d] %-34s correct=TRUE  TM:off=%s on=%s spd=%s  T1:off=%s on=%s spd=%s\n' \
            "$QN" "${#LABELS[@]}" "$id" "$offm" "$onm" "$ratiom" "$off1" "$on1" "$ratio1" >&2
    else
        printf '  [%3d/%d] %-34s correct=FALSE %s\n' "$QN" "${#LABELS[@]}" "$id" "$note" >&2
    fi
done

# ---- Final summary appended to $OUT ----------------------------------------
MNO="$(awk -v s="$SUMNO" -v n="$NNO" 'BEGIN{print (n? s/n : "-")}')"
MYES="$(awk -v s="$SUMYES" -v n="$NYES" 'BEGIN{print (n? s/n : "-")}')"
{
    echo
    echo "============================== SUMMARY ================================"
    echo "queries=$QN  correct=$((QN-NSKIP))  incorrect/skipped=$NSKIP  timed=$NTIMED"
    echo "threads: single=1, multi=${OY_THREADS}"
    echo "  No  (no reorder): n=$NNO  mean speed-up(TM)=$MNO   [expect <=1.0 — SJ overhead, no reorder]"
    echo "  Yes (reorder):   n=$NYES  mean speed-up(TM)=$MYES   [may be >1.0 — reorder/reduction win]"
} >> "$OUT"

echo "Results written to $OUT"
echo "CSV written to $CSV_OUT"