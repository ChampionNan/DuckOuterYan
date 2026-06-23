#!/usr/bin/env bash
# ============================================================================
# experiment_onoff.sh  —  OuterYan ON-vs-OFF correctness + performance test.
#
# Per corpus query, IN THIS ORDER:
#   1. CORRECTNESS GATE — oy_equiv_check (ON==OFF on the bare query). A query that
#      is not equivalence-preserving (or crashes/times out) is NOT timed.
#   2. JOIN_REORDER — oy_regime: No (OuterYan keeps DuckDB's join order) vs
#      Yes (OuterYan reorders), from the join-order signature.
#   3. KERNEL — oy_kernel: which semi-join filter kernel OuterYan committed to
#      (bitmap | hash | mixed | -), from the DUCKDB_SJ_KERNEL_TRACE diagnostic.
#   4. TIMING — oy_time_median off vs on (threads=1 + OY_THREADS, median of 5 runs).
#
# After pass 1, any query that TIMED OUT (gate timeout, or a timing batch that
# produced NA) is re-evaluated once in a RETRY PASS with the timeout multiplied
# by OY_TIMEOUT_RETRY_MULT (default 2 = "doubled"; set 1 to disable). Retry rows
# are appended under their own section (tagged pass=retry in the CSV) and the
# SUMMARY reflects the better, post-retry result.
#
# USAGE: experiment_onoff.sh [options]
#   -b,--bin PATH     duckdb (default build/release/duckdb, else build/debug)
#   -n,--runs N       timed iterations per config (default 5; median taken)
#   -t,--timeout S    per-query timeout sec (default 300; via `timeout`). The
#                     timing batch runs N+1 executions (1 warm-up + N timed) in one
#                     process, so its budget is (N+1)×S; the 1-run gate uses S.
#                     Timed-out queries are retried once at S×OY_TIMEOUT_RETRY_MULT.
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
# One experiment start timestamp, captured the moment this script begins (before
# the DB-build phase). Used for BOTH the .txt/.csv filenames AND the in-file
# header, so the txt, its corresponding csv, and the printed time all agree and
# all read as "when experiment_onoff.sh started". Single `date` call so the
# filename form and human form can never straddle a second boundary.
_now="$(date '+%Y%m%d_%H%M%S|%F %T')"
START_TS="${_now%%|*}"; START_HUMAN="${_now##*|}"
_default_out="$SCRIPT_DIR/results/experiment_onoff_${START_TS}.txt"
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

# --- duckdb process lifecycle / interrupt-safe cleanup ----------------------
# Problem: on Ctrl+C a duckdb that is mid-query could be left running, holding
# the database file open and causing IO errors for the next query. Fix: launch
# duckdb as a DIRECT, tracked background child of this shell and `wait` on it
# (so the next query never starts until the current duckdb has fully exited);
# on any interrupt, a trap TERM/KILLs the tracked duckdb subtree before exiting.
# We only ever signal processes we ourselves started, so this is safe on a
# shared machine (never `pkill duckdb`).
OY_DUCK_PIDS=()

_oy_untrack() {                       # drop a finished pid from the live list
    local p keep=()
    for p in "${OY_DUCK_PIDS[@]:-}"; do
        [ -n "$p" ] && [ "$p" != "$1" ] && keep+=("$p")
    done
    OY_DUCK_PIDS=("${keep[@]:-}")
}

_oy_kill_tree() {                     # _oy_kill_tree <signal> <pid>: kids first
    local sig="$1" pid="$2" c
    for c in $(pgrep -P "$pid" 2>/dev/null); do _oy_kill_tree "$sig" "$c"; done
    kill "-$sig" "$pid" 2>/dev/null || true
}

_oy_cleanup() {
    trap '' INT TERM EXIT             # disable traps: no re-entry while cleaning
    local p alive waited=0
    local had=0; for p in "${OY_DUCK_PIDS[@]:-}"; do [ -n "$p" ] && had=1; done
    [ "$had" = 1 ] && echo "  [cleanup] terminating duckdb (pids: ${OY_DUCK_PIDS[*]})" >&2
    for p in "${OY_DUCK_PIDS[@]:-}"; do [ -n "$p" ] && _oy_kill_tree TERM "$p"; done
    while [ "$waited" -lt 30 ]; do    # up to ~3s grace for a clean TERM exit
        alive=0
        for p in "${OY_DUCK_PIDS[@]:-}"; do
            [ -n "$p" ] && kill -0 "$p" 2>/dev/null && alive=1
        done
        [ "$alive" = 0 ] && break
        sleep 0.1; waited=$((waited+1))
    done
    for p in "${OY_DUCK_PIDS[@]:-}"; do [ -n "$p" ] && _oy_kill_tree KILL "$p"; done
}
trap '_oy_cleanup; exit 130' INT
trap '_oy_cleanup; exit 143' TERM
trap '_oy_cleanup' EXIT

# Invoke duckdb (optionally under `timeout`) as a tracked background child and
# wait for it. Reads SQL from stdin (redirect a file in); args/redirs from the
# caller are inherited by the duckdb child. Returns duckdb's exit code (124 on
# timeout). Must NOT be called inside a pipeline, or the child would belong to
# a transient subshell and escape both PID tracking and the cleanup trap.
oy_duck() {
    local pid rc
    # `<&0` is REQUIRED: a backgrounded command in a non-job-control shell has
    # its stdin redirected from /dev/null unless stdin is explicitly redirected,
    # which would make duckdb read no SQL. `<&0` dups the caller's stdin (the
    # SQL file) into the child so the query actually runs.
    if [ -n "$OY_TIMEOUT_BIN" ]; then
        "$OY_TIMEOUT_BIN" "$OY_TIMEOUT_SECS" "$DUCKDB_BIN" "$@" <&0 &
    else
        "$DUCKDB_BIN" "$@" <&0 &
    fi
    pid=$!
    OY_DUCK_PIDS+=("$pid")
    wait "$pid"; rc=$?
    _oy_untrack "$pid"
    return $rc
}

# --- the correctness atom ---------------------------------------------------
# Runs the SAME query with OuterYan OFF and ON against <db>, compares both
# result sets (multiset + order-independent) via ORDER BY ALL inside DuckDB.
# RETURNS: 0 PASS | 1 FAIL (rows differ) | 2 ERROR | 3 TIMEOUT.
oy_equiv_check() {
    local db="$1" label="$2" query="$3"
    local off on eoff eon sql roff ron rc=0
    off=$(mktemp); on=$(mktemp); eoff=$(mktemp); eon=$(mktemp); sql=$(mktemp)

    local sorted_q="SELECT * FROM (${query%;}) _oy_sub ORDER BY ALL;"

    printf '%s\n%s\n' "$OY_OFF" "$sorted_q" > "$sql"
    oy_duck "$db" -csv -noheader < "$sql" > "$off" 2>"$eoff"; roff=$?
    printf '%s\n%s\n' "$OY_ON"  "$sorted_q" > "$sql"
    oy_duck "$db" -csv -noheader < "$sql" > "$on"  2>"$eon";  ron=$?

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
    rm -f "$off" "$on" "$eoff" "$eon" "$sql"
    return $rc
}

# --- timing -----------------------------------------------------------------
# oy_time_median: run ONE warm-up followed by $runs timed executions, all with the
# timer on, and return the median over the TIMED runs (the warm-up is NOT counted,
# so total executions = $runs + 1). DuckDB flushes each run's "Run Time" line as
# the statement finishes, so if the per-query timeout kills the batch part-way the
# timed runs that already completed are still captured and we report the median
# over THOSE. If the kill lands before any timed run finishes, we fall back to the
# warm-up time so a result is still produced; NA is emitted ONLY when not a single
# run completed within the timeout.
# Output: "median_time runs_used"  (runs_used = how many TIMED runs the median spans)
: "${OY_RUNS:=10}"

oy_time_median() {
    local db="$1" set_sql="$2" query="$3" runs="$4" threads="$5"
    local script i
    script="PRAGMA threads=${threads};"$'\n'"${set_sql}"$'\n'
    # 1 warm-up run + $runs timed runs (timer on for all). The warm-up primes the
    # buffer pool and is excluded from the median; timing it too means a killed
    # batch still has a fallback measurement instead of NA.
    script+=".timer on"$'\n'
    script+="${query%;};"$'\n'                                   # warm-up (not counted)
    for ((i=0; i<runs; i++)); do script+="${query%;};"$'\n'; done
    local times sqlf rawf
    sqlf=$(mktemp); rawf=$(mktemp)
    printf '%s' "$script" > "$sqlf"
    # OY_TIMEOUT_SECS is the PER-QUERY limit. The batch runs $runs+1 executions
    # (1 warm-up + $runs timed) in one process under a single `timeout`, so scale
    # the budget to (runs+1) * per-query so every run gets its full limit. When
    # the global timeout is disabled (OY_TIMEOUT_BIN empty / secs=0) this is moot.
    local saved_to="$OY_TIMEOUT_SECS"
    [ -n "$OY_TIMEOUT_BIN" ] && [ "$OY_TIMEOUT_SECS" != "0" ] \
        && OY_TIMEOUT_SECS=$(( OY_TIMEOUT_SECS * (runs + 1) ))
    oy_duck "$db" -noheader < "$sqlf" > "$rawf" 2>&1
    OY_TIMEOUT_SECS="$saved_to"
    # Run Times in EXECUTION order; the first entry is the warm-up.
    times="$(awk '/Run Time/{for(i=1;i<=NF;i++) if($i=="real") print $(i+1)}' "$rawf")"
    rm -f "$sqlf" "$rawf"
    [ -z "$times" ] && { echo "NA 0"; return; }
    # Median over the timed runs (drop the warm-up); fall back to the warm-up only
    # if it is the lone run that completed, so a number is always reported.
    echo "$times" | awk '
        { t[NR]=$1 }
        END {
            n=NR
            lo=(n>1)?2:1                          # skip the warm-up when a timed run survived
            m=0; for(k=lo;k<=n;k++) a[++m]=t[k]   # timed set, still in run order
            for(i=1;i<=m;i++) for(j=i+1;j<=m;j++) if(a[j]<a[i]){x=a[i];a[i]=a[j];a[j]=x}
            if(m%2==1) med=a[(m+1)/2]; else med=(a[m/2]+a[m/2+1])/2
            printf "%.4f %d", med, m
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

# --- semi-join kernel classification (bitmap vs hash) -----------------------
# Like the join-order regime, the kernel each SJ filter commits to is a
# structural property of how OuterYan executed the query. The kind is decided at
# runtime (PhysicalSJBuild::Finalize, including the bitmap->hash overflow
# fallback), so we cannot read it from EXPLAIN — instead we run the query ONCE
# with OuterYan ON and the C++ kernel trace (env DUCKDB_SJ_KERNEL_TRACE) on, then
# count the per-filter "[SJ_KERNEL] BITMAP|HASH" lines it prints to stderr.
# Echoes: "<label> b<N>h<M>" — label is bitmap | hash | mixed | - (no SJ filters).
oy_kernel() {
    local db="$1" query="$2" sqlf errf nbm nhash label
    sqlf=$(mktemp); errf=$(mktemp)
    printf '%s\n%s\n' "$OY_ON" "${query%;};" > "$sqlf"
    # Scope the trace to this single run: export before, unset after, so the
    # timing/equivalence oy_duck calls never see the extra stderr.
    export DUCKDB_SJ_KERNEL_TRACE=1
    oy_duck "$db" -noheader < "$sqlf" >/dev/null 2>"$errf"
    unset DUCKDB_SJ_KERNEL_TRACE
    nbm="$(grep -c '\[SJ_KERNEL\] BITMAP' "$errf")"
    nhash="$(grep -c '\[SJ_KERNEL\] HASH' "$errf")"
    rm -f "$sqlf" "$errf"
    if   [ "$nbm" -gt 0 ] && [ "$nhash" -gt 0 ]; then label="mixed"
    elif [ "$nbm" -gt 0 ]; then label="bitmap"
    elif [ "$nhash" -gt 0 ]; then label="hash"
    else label="-"; fi
    echo "$label b${nbm}h${nhash}"
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
    echo "# OuterYan on/off experiment   started $START_HUMAN"
    echo "# binary : $DUCKDB_BIN"
    echo "# corpus : $ONLY  (pattern=$PATTERN limit=$LIMIT) — ${#LABELS[@]} queries from $CORPUS"
    echo "# tables : $SIZES"
    echo "# timing : threads=1+${OY_THREADS}, median of ${RUNS} runs per config (1 warm-up + ${RUNS} timed)"
    echo "# timeout: ${OY_TIMEOUT_SECS}s/query → timing batch gets $(( OY_TIMEOUT_SECS * (RUNS + 1) ))s ((RUNS+1)×); timed-out queries retried once at ×${OY_TIMEOUT_RETRY_MULT:-2}"
    echo "# correct: ON result multiset == OFF result; only correct queries are timed"
    echo
    echo "===================== LIVE PER-QUERY RESULTS =========================="
    echo "# Columns: T1 = single-thread, TM = multi-thread (threads=${OY_THREADS})"
    echo "#   kernel = semi-join filter kernel OuterYan ran: bitmap | hash | mixed | - (no SJ)"
    printf '%-34s %-5s %-7s %-9s %-10s %9s %9s %7s %9s %9s %7s\n' \
        query reord? kernel correct note T1:off T1:on T1:spd TM:off TM:on TM:spd
    echo "----------------------------------------------------------------------"
} > "$OUT"

echo "query,reorder,kernel,kernel_detail,correct,note,t1_off,t1_on,t1_speedup,tm_off,tm_on,tm_speedup,rows,pass" > "$CSV_OUT"

# Per-query state arrays (index = query #). Written by process_one and read by
# the final summary, so that a RETRY-pass result OVERWRITES the first-pass value
# at the same index and the summary reflects the post-retry outcome.
QLBL=(); QNREL=(); QCORRECT=(); QNOTE=(); QROWS=(); QREG=()
QDB=(); QSQL=(); QKER=(); QKDETAIL=()
QOFF1=(); QON1=(); QRATIO1=()
QOFFM=(); QONM=(); QRATIOM=()

PASS="main"            # "main" | "retry": value of the CSV `pass` column
OY_LAST_TIMEDOUT=0     # set by process_one: 1 iff query i hit a timeout/NA

# process_one <i> — run the full pipeline for query i (gate -> regime -> kernel
# -> timing) under the CURRENT $OY_TIMEOUT_SECS, store the result in the Q*
# arrays at index i, and append one row to $OUT and $CSV_OUT (tagged $PASS).
# Sets OY_LAST_TIMEDOUT=1 when query i timed out — gate TIMEOUT, or a timing
# batch that returned NA (the `timeout` killed the process) — so the caller can
# queue it for the doubled-timeout retry pass.
process_one() {
    local i="$1"
    local id="${LABELS[i]}" sql="${SQLS[i]}" db="${DBS[i]}"
    local nrel="-"; case "$id" in *_N[0-9]*) nrel="$(printf '%s' "$id" | sed -nE 's/.*_N([0-9]+)_.*/\1/p')";; esac
    local gate correct note rows
    gate="$(oy_equiv_check "$db" "$id" "$sql")"
    case "$gate" in
        *"equiv OK"*)  correct="TRUE";  note="OK";        rows="$(printf '%s' "$gate" | grep -oE '[0-9]+ rows' | grep -oE '[0-9]+')";;
        *"NOT EQUIV"*) correct="FALSE"; note="NOT-EQUIV"; rows="$(printf '%s' "$gate" | grep -oE 'off=[0-9]+ on=[0-9]+')";;
        *"TIMEOUT"*)   correct="FALSE"; note="TIMEOUT";   rows="-";;
        *)             correct="FALSE"; note="ERROR";     rows="-";;
    esac
    local reg="-" ker="-" kdetail="-" offm="-" onm="-" ratiom="-" off1="-" on1="-" ratio1="-"
    OY_LAST_TIMEDOUT=0
    if [ "$correct" = "TRUE" ]; then
        reg="$(oy_regime "$db" "$sql")"; reg="${reg%% *}"
        local kraw; kraw="$(oy_kernel "$db" "$sql")"; ker="${kraw%% *}"; kdetail="${kraw##* }"
        local local_rom local_rnm local_ro1 local_rn1
        local_rom="$(oy_time_median "$db" "$OY_OFF" "$sql" "$RUNS" "${OY_THREADS}")"
        local_rnm="$(oy_time_median "$db" "$OY_ON"  "$sql" "$RUNS" "${OY_THREADS}")"
        offm="$(echo "$local_rom" | awk '{print $1}')"; onm="$(echo "$local_rnm" | awk '{print $1}')"
        ratiom="$(awk -v off="$offm" -v on="$onm" 'BEGIN{ if(off!="NA"&&on!="NA"&&on+0>0) printf "%.3f", off/on; else print "NA" }')"
        local_ro1="$(oy_time_median "$db" "$OY_OFF" "$sql" "$RUNS" 1)"
        local_rn1="$(oy_time_median "$db" "$OY_ON"  "$sql" "$RUNS" 1)"
        off1="$(echo "$local_ro1" | awk '{print $1}')"; on1="$(echo "$local_rn1" | awk '{print $1}')"
        ratio1="$(awk -v off="$off1" -v on="$on1" 'BEGIN{ if(off!="NA"&&on!="NA"&&on+0>0) printf "%.3f", off/on; else print "NA" }')"
        # a timing batch killed by `timeout` yields NA -> retry candidate
        case "$offm$onm$off1$on1" in *NA*) OY_LAST_TIMEDOUT=1;; esac
    elif [ "$note" = "TIMEOUT" ]; then
        OY_LAST_TIMEDOUT=1
    fi
    # store final state (RETRY overwrites first-pass values at the same index)
    QLBL[$i]="$id"; QNREL[$i]="$nrel"; QCORRECT[$i]="$correct"; QNOTE[$i]="$note"; QROWS[$i]="$rows"
    QREG[$i]="$reg"; QDB[$i]="$db"; QSQL[$i]="$sql"; QKER[$i]="$ker"; QKDETAIL[$i]="$kdetail"
    QOFFM[$i]="$offm"; QONM[$i]="$onm"; QRATIOM[$i]="$ratiom"
    QOFF1[$i]="$off1"; QON1[$i]="$on1"; QRATIO1[$i]="$ratio1"
    # ---- append to $OUT and $CSV_OUT ----
    printf '%-34s %-5s %-7s %-9s %-10s %9s %9s %7s %9s %9s %7s\n' \
        "$id" "$reg" "$ker" "$correct" "$note" "$off1" "$on1" "$ratio1" "$offm" "$onm" "$ratiom" >> "$OUT"
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$id" "$reg" "$ker" "$kdetail" "$correct" "$note" "$off1" "$on1" "$ratio1" "$offm" "$onm" "$ratiom" "$rows" "$PASS" >> "$CSV_OUT"
    local rtag=""; [ "$PASS" = "retry" ] && rtag="  (retry @${OY_TIMEOUT_SECS}s)"
    if [ "$correct" = "TRUE" ]; then
        printf '  [%3d/%d] %-34s correct=TRUE  TM:off=%s on=%s spd=%s  T1:off=%s on=%s spd=%s%s\n' \
            "$((i+1))" "${#LABELS[@]}" "$id" "$offm" "$onm" "$ratiom" "$off1" "$on1" "$ratio1" "$rtag" >&2
    else
        printf '  [%3d/%d] %-34s correct=FALSE %s%s\n' "$((i+1))" "${#LABELS[@]}" "$id" "$note" "$rtag" >&2
    fi
}

# ==== Pass 1: every query under the base timeout ============================
echo "--- Per-query: correctness + multi-thread (TM=${OY_THREADS}) + single-thread (T1=1) ---" >&2
RETRY_IDX=()
for ((i=0; i<${#LABELS[@]}; i++)); do
    process_one "$i"
    [ "$OY_LAST_TIMEDOUT" = 1 ] && RETRY_IDX+=("$i")
done

# ==== Pass 2 (retry): re-evaluate timed-out queries with a DOUBLED timeout ===
# Each query that timed out under the base limit is re-run once with the timeout
# multiplied by OY_TIMEOUT_RETRY_MULT (default 2). Rows are appended under a
# clearly-labelled section and tagged pass=retry in the CSV; the Q* arrays (and
# thus the SUMMARY below) are overwritten with the better, post-retry result.
BASE_TIMEOUT="$OY_TIMEOUT_SECS"
RETRY_MULT="${OY_TIMEOUT_RETRY_MULT:-2}"
NRETRY=0; NRECOVERED=0; RETRY_TO=""
if [ "${#RETRY_IDX[@]}" -gt 0 ] && [ -n "$OY_TIMEOUT_BIN" ] \
   && [ "$BASE_TIMEOUT" != "0" ] && [ "$RETRY_MULT" -gt 1 ] 2>/dev/null; then
    RETRY_TO=$(( BASE_TIMEOUT * RETRY_MULT ))
    NRETRY="${#RETRY_IDX[@]}"
    {
        echo
        echo "============== RETRY PASS (timeout ${BASE_TIMEOUT}s ×${RETRY_MULT} = ${RETRY_TO}s) =============="
        echo "# ${NRETRY} query(ies) timed out under ${BASE_TIMEOUT}s; re-evaluated below with ${RETRY_TO}s."
    } >> "$OUT"
    echo "--- RETRY: ${NRETRY} timed-out query(ies) with timeout=${RETRY_TO}s ---" >&2
    PASS="retry"; export OY_TIMEOUT_SECS="$RETRY_TO"
    for i in "${RETRY_IDX[@]}"; do
        process_one "$i"
        [ "$OY_LAST_TIMEDOUT" = 0 ] && NRECOVERED=$((NRECOVERED+1))
    done
    export OY_TIMEOUT_SECS="$BASE_TIMEOUT"; PASS="main"
fi

# ==== Final summary computed from the Q* arrays (reflects retry results) =====
QN="${#LABELS[@]}"
NCORRECT=0; NTIMED=0; NKBM=0; NKHASH=0; NKMIX=0
NNO=0; NYES=0; SUMNO=0; SUMYES=0
for ((i=0; i<QN; i++)); do
    [ "${QCORRECT[i]}" = "TRUE" ] || continue
    NCORRECT=$((NCORRECT+1)); NTIMED=$((NTIMED+1))
    case "${QKER[i]}" in bitmap) NKBM=$((NKBM+1));; hash) NKHASH=$((NKHASH+1));; mixed) NKMIX=$((NKMIX+1));; esac
    [ "${QRATIOM[i]}" = "NA" ] && continue
    if [ "${QREG[i]}" = "No" ]; then NNO=$((NNO+1));  SUMNO="$(awk -v s="$SUMNO" -v r="${QRATIOM[i]}" 'BEGIN{print s+r}')"
    else                             NYES=$((NYES+1)); SUMYES="$(awk -v s="$SUMYES" -v r="${QRATIOM[i]}" 'BEGIN{print s+r}')"; fi
done
NSKIP=$((QN-NCORRECT))
MNO="$(awk -v s="$SUMNO" -v n="$NNO" 'BEGIN{print (n? s/n : "-")}')"
MYES="$(awk -v s="$SUMYES" -v n="$NYES" 'BEGIN{print (n? s/n : "-")}')"
{
    echo
    echo "============================== SUMMARY ================================"
    echo "queries=$QN  correct=$NCORRECT  incorrect/skipped=$NSKIP  timed=$NTIMED"
    echo "kernel (correct queries): bitmap=$NKBM  hash=$NKHASH  mixed=$NKMIX"
    [ "$NRETRY" -gt 0 ] && echo "retry pass: $NRETRY timed-out query(ies) re-run at ${RETRY_TO}s — $NRECOVERED now fully timed, $((NRETRY-NRECOVERED)) still timing out / partial (see retry rows above)"
    echo "threads: single=1, multi=${OY_THREADS}"
    echo "  No  (no reorder): n=$NNO  mean speed-up(TM)=$MNO   [expect <=1.0 — SJ overhead, no reorder]"
    echo "  Yes (reorder):   n=$NYES  mean speed-up(TM)=$MYES   [may be >1.0 — reorder/reduction win]"
} >> "$OUT"

echo "Results written to $OUT"
echo "CSV written to $CSV_OUT"