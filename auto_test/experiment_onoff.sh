#!/usr/bin/env bash
# ============================================================================
# experiment_onoff.sh  —  OuterYan ON-vs-OFF correctness + performance test.
#
# Per corpus query, IN THIS ORDER:
#   1. CORRECTNESS GATE — oy_equiv_check (ON==OFF on the bare query). A query that
#      is not equivalence-preserving (or crashes/times out) is NOT timed.
#   2. PLAN DECISION — oy_decision reads OuterYan's machine-readable trace:
#      whether its candidate grouping differs from DuckDB, whether the cost gate
#      ran, and which candidate was selected.
#   3. KERNEL — oy_kernel: which semi-join filter kernel OuterYan committed to
#      (bitmap | hash | mixed | -), from the DUCKDB_SJ_KERNEL_TRACE diagnostic.
#   4. TIMING — oy_time_median off vs on (threads=1 + OY_THREADS, median of 5 runs).
#   5. PHASE PROFILE — one single-thread ON run, reporting categorized operator
#      elapsed seconds for round-1 semi-joins, round-2 semi-joins, and real joins.
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
# This is the hard PRE-CONDITION run before any timing: a query that is not
# verified here (mismatch / error / timeout) is NOT timed. It runs in PARALLEL
# (threads=OY_THREADS) so it returns fast, and gets 2x the per-query timeout
# because it also sorts the entire result (ORDER BY ALL) for the multiset compare.
# RETURNS: 0 PASS | 1 FAIL (rows differ) | 2 ERROR | 3 TIMEOUT.
oy_equiv_check() {
    local db="$1" label="$2" query="$3"
    local off on eoff eon sql roff ron rc=0
    off=$(mktemp); on=$(mktemp); eoff=$(mktemp); eon=$(mktemp); sql=$(mktemp)

    local sorted_q="SELECT * FROM (${query%;}) _oy_sub ORDER BY ALL;"
    local prag="PRAGMA threads=${OY_THREADS};"
    # gate timeout = 2 x per-query limit (only while the timeout is enabled)
    local saved_to="$OY_TIMEOUT_SECS" gate_to="$OY_TIMEOUT_SECS"
    if [ -n "$OY_TIMEOUT_BIN" ] && [ "$OY_TIMEOUT_SECS" != "0" ]; then
        gate_to=$(( OY_TIMEOUT_SECS * 2 )); OY_TIMEOUT_SECS="$gate_to"
    fi

    printf '%s\n%s\n%s\n' "$prag" "$OY_OFF" "$sorted_q" > "$sql"
    oy_duck "$db" -csv -noheader < "$sql" > "$off" 2>"$eoff"; roff=$?
    printf '%s\n%s\n%s\n' "$prag" "$OY_ON"  "$sorted_q" > "$sql"
    oy_duck "$db" -csv -noheader < "$sql" > "$on"  2>"$eon";  ron=$?
    OY_TIMEOUT_SECS="$saved_to"

    if [ "${roff:-0}" -eq 124 ] || [ "${ron:-0}" -eq 124 ]; then
        echo "  TIMEOUT (${gate_to}s): $label"; rc=3
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

# --- OuterYan candidate decision --------------------------------------------
# OuterYan emits exactly one machine-readable record while optimizing EXPLAIN:
#   [OY_DECISION] outer_reordered=0|1 cost_gate_applied=0|1 \
#                 outer_yan_selected=0|1 reason=UPPER_SNAKE_TOKEN \
#                 baseline_cost=N|NA candidate_join_cost=N|NA \
#                 semijoin_raw_cost=N|NA semijoin_cost_ratio=N|NA \
#                 weighted_semijoin_cost=N|NA candidate_total=N|NA \
#                 cost_ratio_limit=N|NA baseline_threshold=N|NA \
#                 round1_build=N|NA round1_probe=N|NA \
#                 round2_build=N|NA round2_probe=N|NA
#
# Results are returned through globals so oy_duck runs in this shell and remains
# covered by the PID-tracking/interrupt cleanup above.
OY_DECISION_REORDERED="NA"
OY_DECISION_GATE="NA"
OY_DECISION_SELECTED="NA"
OY_DECISION_REASON="TRACE_MISSING"
OY_DECISION_BASELINE_COST="NA"
OY_DECISION_CANDIDATE_JOIN_COST="NA"
OY_DECISION_SEMIJOIN_RAW_COST="NA"
OY_DECISION_SEMIJOIN_COST_RATIO="NA"
OY_DECISION_WEIGHTED_SEMIJOIN_COST="NA"
OY_DECISION_CANDIDATE_TOTAL="NA"
OY_DECISION_COST_RATIO_LIMIT="NA"
OY_DECISION_BASELINE_THRESHOLD="NA"
OY_DECISION_ROUND1_BUILD="NA"
OY_DECISION_ROUND1_PROBE="NA"
OY_DECISION_ROUND2_BUILD="NA"
OY_DECISION_ROUND2_PROBE="NA"

oy_decision() {
    local db="$1" query="$2" sqlf tracef rc parsed
    local trace_was_set trace_saved
    sqlf=$(mktemp); tracef=$(mktemp)
    printf '%s\nEXPLAIN (FORMAT json) %s;\n' "$OY_ON" "${query%;}" > "$sqlf"

    # Each probe launches a fresh DuckDB process, so OuterYanTrace's process-wide
    # cached path resolves to this query's private trace file. Preserve a caller's
    # pre-existing trace setting instead of leaking our temporary path.
    trace_was_set="${DUCKDB_OYTRACE+x}"
    trace_saved="${DUCKDB_OYTRACE-}"
    export DUCKDB_OYTRACE="$tracef"
    oy_duck "$db" -noheader < "$sqlf" >/dev/null 2>&1
    rc=$?
    if [ "$trace_was_set" = "x" ]; then
        export DUCKDB_OYTRACE="$trace_saved"
    else
        unset DUCKDB_OYTRACE
    fi

    # Take the last complete valid record. Anchoring the prefix avoids parsing
    # human-readable Stage bodies, and validation makes format drift visible as
    # TRACE_MISSING rather than silently misclassifying a plan.
    parsed="$(awk '
        /^\[OY_DECISION\][[:space:]]/ {
            o=g=s=r=b=j=m=q=w=t=l=h=b1=p1=b2=p2=""
            for (i=2; i<=NF; i++) {
                split($i, kv, "=")
                if      (kv[1]=="outer_reordered")      o=kv[2]
                else if (kv[1]=="cost_gate_applied")    g=kv[2]
                else if (kv[1]=="outer_yan_selected")   s=kv[2]
                else if (kv[1]=="reason")               r=kv[2]
                else if (kv[1]=="baseline_cost")        b=kv[2]
                else if (kv[1]=="candidate_join_cost")  j=kv[2]
                else if (kv[1]=="semijoin_raw_cost")    m=kv[2]
                else if (kv[1]=="semijoin_cost_ratio")  q=kv[2]
                else if (kv[1]=="weighted_semijoin_cost") w=kv[2]
                else if (kv[1]=="candidate_total")      t=kv[2]
                else if (kv[1]=="cost_ratio_limit")     l=kv[2]
                else if (kv[1]=="baseline_threshold")   h=kv[2]
                else if (kv[1]=="round1_build")         b1=kv[2]
                else if (kv[1]=="round1_probe")         p1=kv[2]
                else if (kv[1]=="round2_build")         b2=kv[2]
                else if (kv[1]=="round2_probe")         p2=kv[2]
            }
            number="^[-+]?[0-9]+([.][0-9]+)?([eE][-+]?[0-9]+)?$"
            if (o ~ /^[01]$/ && g ~ /^[01]$/ && s ~ /^[01]$/ &&
                r ~ /^[A-Z0-9_]+$/ &&
                (b=="NA" || b ~ number) && (j=="NA" || j ~ number) &&
                (m=="NA" || m ~ number) && (q=="NA" || q ~ number) &&
                (w=="NA" || w ~ number) && (t=="NA" || t ~ number) &&
                (l=="NA" || l ~ number) && (h=="NA" || h ~ number) &&
                (b1=="NA" || b1 ~ number) && (p1=="NA" || p1 ~ number) &&
                (b2=="NA" || b2 ~ number) && (p2=="NA" || p2 ~ number)) {
                last=o " " g " " s " " r " " b " " j " " m " " q " " w " " t \
                     " " l " " h " " b1 " " p1 " " b2 " " p2
            }
        }
        END { if (last != "") print last }
    ' "$tracef")"
    rm -f "$sqlf" "$tracef"

    OY_DECISION_REORDERED="NA"
    OY_DECISION_GATE="NA"
    OY_DECISION_SELECTED="NA"
    OY_DECISION_BASELINE_COST="NA"
    OY_DECISION_CANDIDATE_JOIN_COST="NA"
    OY_DECISION_SEMIJOIN_RAW_COST="NA"
    OY_DECISION_SEMIJOIN_COST_RATIO="NA"
    OY_DECISION_WEIGHTED_SEMIJOIN_COST="NA"
    OY_DECISION_CANDIDATE_TOTAL="NA"
    OY_DECISION_COST_RATIO_LIMIT="NA"
    OY_DECISION_BASELINE_THRESHOLD="NA"
    OY_DECISION_ROUND1_BUILD="NA"
    OY_DECISION_ROUND1_PROBE="NA"
    OY_DECISION_ROUND2_BUILD="NA"
    OY_DECISION_ROUND2_PROBE="NA"
    if [ "$rc" -eq 0 ]; then
        OY_DECISION_REASON="TRACE_MISSING"
    else
        OY_DECISION_REASON="TRACE_ERROR"
    fi
    if [ -n "$parsed" ]; then
        read -r OY_DECISION_REORDERED OY_DECISION_GATE \
            OY_DECISION_SELECTED OY_DECISION_REASON \
            OY_DECISION_BASELINE_COST OY_DECISION_CANDIDATE_JOIN_COST \
            OY_DECISION_SEMIJOIN_RAW_COST OY_DECISION_SEMIJOIN_COST_RATIO \
            OY_DECISION_WEIGHTED_SEMIJOIN_COST OY_DECISION_CANDIDATE_TOTAL \
            OY_DECISION_COST_RATIO_LIMIT OY_DECISION_BASELINE_THRESHOLD \
            OY_DECISION_ROUND1_BUILD OY_DECISION_ROUND1_PROBE \
            OY_DECISION_ROUND2_BUILD OY_DECISION_ROUND2_PROBE <<< "$parsed"
    fi
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

# Profile one OuterYan-ON execution and sum DuckDB's per-operator elapsed timing
# into three categories. Dynamic physical operator names distinguish the two SJ
# rounds; real joins are identified from their physical operator type. The caller
# uses threads=1 so concurrent worker durations are not added together. These are
# categorized operator timings, not a complete wall-time decomposition.
# Echoes: "round1_s round2_s real_join_s" (NA triplet on failure).
oy_phase_profile() {
    local db="$1" query="$2" threads="$3" sqlf profiledir profilef
    sqlf=$(mktemp)
    profiledir=$(mktemp -d /tmp/oy_profile.XXXXXX)
    profilef="$profiledir/profile.json"
    printf "PRAGMA threads=%s;\n%s\nPRAGMA enable_profiling='json';\nPRAGMA profiling_output='%s';\n%s;\n" \
        "$threads" "$OY_ON" "$profilef" "${query%;}" > "$sqlf"
    oy_duck "$db" -noheader < "$sqlf" >/dev/null 2>&1
    if [ ! -s "$profilef" ]; then
        echo "NA NA NA"
    else
        python3 - "$profilef" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    root = json.load(f)

totals = [0.0, 0.0, 0.0]
stack = list(root.get("children", []))
while stack:
    node = stack.pop()
    stack.extend(node.get("children", []))
    name = node.get("operator_name", "")
    op_type = node.get("operator_type", "")
    timing = float(node.get("operator_timing", 0.0) or 0.0)
    if name in ("SJ_BUILD_ROUND_1", "SJ_PROBE_ROUND_1"):
        totals[0] += timing
    elif name in ("SJ_BUILD_ROUND_2", "SJ_PROBE_ROUND_2"):
        totals[1] += timing
    elif op_type != "SJ_PROBE" and (op_type.endswith("_JOIN") or op_type == "CROSS_PRODUCT"):
        totals[2] += timing
print("{:.6f} {:.6f} {:.6f}".format(*totals))
PY
    fi
    rm -f "$sqlf" "$profilef"
    rmdir "$profiledir" 2>/dev/null || true
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
    # Reuse an existing small graph DB by default. Set
    # OY_FORCE_GRAPH_REBUILD=1 when a fresh dataset build is intentional.
    FORCE="${OY_FORCE_GRAPH_REBUILD:-0}" bash "$BUILD_DB" graph 2>/dev/null || true
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
# RUN: gate -> decision -> kernel/profile/time, streaming to $OUT and $CSV_OUT
# ============================================================================
CSV_OUT="${OUT%.txt}.csv"

# Header (truncate + write)
{
    echo "# OuterYan on/off experiment   started $START_HUMAN"
    echo "# binary : $DUCKDB_BIN"
    echo "# corpus : $ONLY  (pattern=$PATTERN limit=$LIMIT) — ${#LABELS[@]} queries from $CORPUS"
    echo "# tables : $SIZES"
    echo "# timing : threads=1+${OY_THREADS}, median of ${RUNS} runs per config (1 warm-up + ${RUNS} timed)"
    echo "# phases : one profiled ON run at threads=1; R1SJ-T1/R2SJ-T1/JOIN-T1 are summed categorized operator elapsed seconds"
    echo "#          they exclude uncategorized/unprofiled work and need not sum to T1:on"
    echo "# timeout: ${OY_TIMEOUT_SECS}s/query → correctness gate gets $(( OY_TIMEOUT_SECS * 2 ))s (2×, parallel threads=${OY_THREADS}), timing batch gets $(( OY_TIMEOUT_SECS * (RUNS + 1) ))s ((RUNS+1)×); timed-out queries retried once at ×${OY_TIMEOUT_RETRY_MULT:-2}"
    echo "# correct: ON result multiset == OFF result; only correct queries are timed"
    echo
    echo "===================== LIVE PER-QUERY RESULTS =========================="
    echo "# Columns: T1 = single-thread, TM = multi-thread (threads=${OY_THREADS})"
    echo "#   outer/gate/useOY = reordered vs DuckDB / cost comparison applied / OuterYan selected (0|1)"
    echo "#   cost estimates are printed on the indented line following each correct query"
    echo "#   kernel = semi-join filter kernel OuterYan ran: bitmap | hash | mixed | - (no SJ)"
    printf '%-34s %-4s %-4s %-5s %-20s %-7s %-9s %-10s %9s %9s %7s %9s %9s %7s %9s %9s %9s\n' \
        query outer gate useOY decision kernel correct note T1:off T1:on T1:spd TM:off TM:on TM:spd R1SJ-T1 R2SJ-T1 JOIN-T1
    echo "----------------------------------------------------------------------"
} > "$OUT"

# `reorder` is retained for plot_speedup.py compatibility. It is Yes exactly
# when `outer_reordered=1`; `outer_yan_selected` independently records whether
# that candidate survived the optional cost gate and was actually executed.
echo "query,reorder,outer_reordered,cost_gate_applied,outer_yan_selected,decision_reason,baseline_cost,candidate_join_cost,semijoin_raw_cost,semijoin_cost_ratio,weighted_semijoin_cost,candidate_total,cost_ratio_limit,baseline_threshold,round1_build,round1_probe,round2_build,round2_probe,kernel,kernel_detail,correct,note,t1_off,t1_on,t1_speedup,tm_off,tm_on,tm_speedup,t1_round1_sj_operator_elapsed_s,t1_round2_sj_operator_elapsed_s,t1_real_join_operator_elapsed_s,rows,pass" > "$CSV_OUT"

# Per-query state arrays (index = query #). Written by process_one and read by
# the final summary, so that a RETRY-pass result OVERWRITES the first-pass value
# at the same index and the summary reflects the post-retry outcome.
QLBL=(); QNREL=(); QCORRECT=(); QNOTE=(); QROWS=(); QREG=()
QDB=(); QSQL=(); QKER=(); QKDETAIL=()
QREORDERED=(); QGATE=(); QSELECTED=(); QDECISION=()
QBASELINE_COST=(); QCANDIDATE_JOIN_COST=(); QSEMIJOIN_RAW_COST=(); QSEMIJOIN_COST_RATIO=()
QWEIGHTED_SEMIJOIN_COST=(); QCANDIDATE_TOTAL=()
QCOST_RATIO_LIMIT=(); QBASELINE_THRESHOLD=()
QROUND1_BUILD=(); QROUND1_PROBE=(); QROUND2_BUILD=(); QROUND2_PROBE=()
QOFF1=(); QON1=(); QRATIO1=()
QOFFM=(); QONM=(); QRATIOM=()
QR1SJ=(); QR2SJ=(); QREALJOIN=()

PASS="main"            # "main" | "retry": value of the CSV `pass` column
OY_LAST_TIMEDOUT=0     # set by process_one: 1 iff query i hit a timeout/NA

# process_one <i> — run the full pipeline for query i (gate -> decision -> kernel
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
    local reg="-" outer_reordered="-" gate_applied="-" selected="-" decision="-"
    local baseline_cost="-" candidate_join_cost="-" semijoin_raw_cost="-"
    local semijoin_cost_ratio="-" weighted_semijoin_cost="-" candidate_total="-"
    local cost_ratio_limit="-" baseline_threshold="-"
    local round1_build="-" round1_probe="-" round2_build="-" round2_probe="-"
    local ker="-" kdetail="-" offm="-" onm="-" ratiom="-" off1="-" on1="-" ratio1="-"
    local r1sj="-" r2sj="-" realjoin="-"
    OY_LAST_TIMEDOUT=0
    if [ "$correct" = "TRUE" ]; then
        oy_decision "$db" "$sql"
        outer_reordered="$OY_DECISION_REORDERED"
        gate_applied="$OY_DECISION_GATE"
        selected="$OY_DECISION_SELECTED"
        decision="$OY_DECISION_REASON"
        baseline_cost="$OY_DECISION_BASELINE_COST"
        candidate_join_cost="$OY_DECISION_CANDIDATE_JOIN_COST"
        semijoin_raw_cost="$OY_DECISION_SEMIJOIN_RAW_COST"
        semijoin_cost_ratio="$OY_DECISION_SEMIJOIN_COST_RATIO"
        weighted_semijoin_cost="$OY_DECISION_WEIGHTED_SEMIJOIN_COST"
        candidate_total="$OY_DECISION_CANDIDATE_TOTAL"
        cost_ratio_limit="$OY_DECISION_COST_RATIO_LIMIT"
        baseline_threshold="$OY_DECISION_BASELINE_THRESHOLD"
        round1_build="$OY_DECISION_ROUND1_BUILD"
        round1_probe="$OY_DECISION_ROUND1_PROBE"
        round2_build="$OY_DECISION_ROUND2_BUILD"
        round2_probe="$OY_DECISION_ROUND2_PROBE"
        case "$outer_reordered" in 1) reg="Yes";; 0) reg="No";; *) reg="-";; esac
        if [ "$selected" = "1" ]; then
            local kraw; kraw="$(oy_kernel "$db" "$sql")"; ker="${kraw%% *}"; kdetail="${kraw##* }"
        else
            ker="-"; kdetail="b0h0"
        fi
        local praw; praw="$(oy_phase_profile "$db" "$sql" 1)"
        r1sj="$(echo "$praw" | awk '{print $1}')"
        r2sj="$(echo "$praw" | awk '{print $2}')"
        realjoin="$(echo "$praw" | awk '{print $3}')"
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
    QREORDERED[$i]="$outer_reordered"; QGATE[$i]="$gate_applied"; QSELECTED[$i]="$selected"; QDECISION[$i]="$decision"
    QBASELINE_COST[$i]="$baseline_cost"; QCANDIDATE_JOIN_COST[$i]="$candidate_join_cost"
    QSEMIJOIN_RAW_COST[$i]="$semijoin_raw_cost"; QSEMIJOIN_COST_RATIO[$i]="$semijoin_cost_ratio"
    QWEIGHTED_SEMIJOIN_COST[$i]="$weighted_semijoin_cost"; QCANDIDATE_TOTAL[$i]="$candidate_total"
    QCOST_RATIO_LIMIT[$i]="$cost_ratio_limit"; QBASELINE_THRESHOLD[$i]="$baseline_threshold"
    QROUND1_BUILD[$i]="$round1_build"; QROUND1_PROBE[$i]="$round1_probe"
    QROUND2_BUILD[$i]="$round2_build"; QROUND2_PROBE[$i]="$round2_probe"
    QOFFM[$i]="$offm"; QONM[$i]="$onm"; QRATIOM[$i]="$ratiom"
    QOFF1[$i]="$off1"; QON1[$i]="$on1"; QRATIO1[$i]="$ratio1"
    QR1SJ[$i]="$r1sj"; QR2SJ[$i]="$r2sj"; QREALJOIN[$i]="$realjoin"
    # ---- append to $OUT and $CSV_OUT ----
    printf '%-34s %-4s %-4s %-5s %-20s %-7s %-9s %-10s %9s %9s %7s %9s %9s %7s %9s %9s %9s\n' \
        "$id" "$outer_reordered" "$gate_applied" "$selected" "$decision" "$ker" "$correct" "$note" \
        "$off1" "$on1" "$ratio1" "$offm" "$onm" "$ratiom" "$r1sj" "$r2sj" "$realjoin" >> "$OUT"
    if [ "$correct" = "TRUE" ]; then
        printf '  cost: baseline=%s threshold=%s (ratio=%s) candidate_join=%s semijoin_raw=%s semijoin_ratio=%s semijoin_weighted=%s candidate_total=%s  R1(build=%s probe=%s) R2(build=%s probe=%s)\n' \
            "$baseline_cost" "$baseline_threshold" "$cost_ratio_limit" \
            "$candidate_join_cost" "$semijoin_raw_cost" "$semijoin_cost_ratio" \
            "$weighted_semijoin_cost" "$candidate_total" \
            "$round1_build" "$round1_probe" "$round2_build" "$round2_probe" >> "$OUT"
        if [ "$gate_applied" = "1" ]; then
            local comparison_result="FAIL"
            [ "$selected" = "1" ] && comparison_result="PASS"
            printf '  gate formula: candidate_join + semijoin_ratio * semijoin_raw <= baseline_ratio * baseline\n' >> "$OUT"
            printf '  gate values:  %s + %s * %s <= %s * %s\n' \
                "$candidate_join_cost" "$semijoin_cost_ratio" "$semijoin_raw_cost" \
                "$cost_ratio_limit" "$baseline_cost" >> "$OUT"
            printf '  gate result:  %s <= %s => %s -> %s\n' \
                "$candidate_total" "$baseline_threshold" "$comparison_result" "$decision" >> "$OUT"
        else
            printf '  gate: skipped -> %s\n' "$decision" >> "$OUT"
        fi
    fi
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$id" "$reg" "$outer_reordered" "$gate_applied" "$selected" "$decision" \
        "$baseline_cost" "$candidate_join_cost" "$semijoin_raw_cost" "$semijoin_cost_ratio" \
        "$weighted_semijoin_cost" "$candidate_total" \
        "$cost_ratio_limit" "$baseline_threshold" \
        "$round1_build" "$round1_probe" "$round2_build" "$round2_probe" \
        "$ker" "$kdetail" "$correct" "$note" "$off1" "$on1" "$ratio1" \
        "$offm" "$onm" "$ratiom" "$r1sj" "$r2sj" "$realjoin" "$rows" "$PASS" >> "$CSV_OUT"
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
NBASELINE=0; NOUTERYAN=0; SUMBASELINE=0; SUMOUTERYAN=0
NSAME=0; NREJECT=0; NSELECTED=0; NDECISION_UNKNOWN=0; NGATE_APPLIED=0
NPHASE=0; SUMR1=0; SUMR2=0; SUMJOIN=0
for ((i=0; i<QN; i++)); do
    [ "${QCORRECT[i]}" = "TRUE" ] || continue
    NCORRECT=$((NCORRECT+1)); NTIMED=$((NTIMED+1))
    case "${QKER[i]}" in bitmap) NKBM=$((NKBM+1));; hash) NKHASH=$((NKHASH+1));; mixed) NKMIX=$((NKMIX+1));; esac
    [ "${QGATE[i]}" = "1" ] && NGATE_APPLIED=$((NGATE_APPLIED+1))
    case "${QREORDERED[i]}:${QSELECTED[i]}" in
        0:0) NSAME=$((NSAME+1));;
        1:0) NREJECT=$((NREJECT+1));;
        1:1) NSELECTED=$((NSELECTED+1));;
        *)   NDECISION_UNKNOWN=$((NDECISION_UNKNOWN+1));;
    esac
    if [ "${QR1SJ[i]}" != "NA" ] && [ "${QR1SJ[i]}" != "-" ]; then
        NPHASE=$((NPHASE+1))
        SUMR1="$(awk -v s="$SUMR1" -v v="${QR1SJ[i]}" 'BEGIN{print s+v}')"
        SUMR2="$(awk -v s="$SUMR2" -v v="${QR2SJ[i]}" 'BEGIN{print s+v}')"
        SUMJOIN="$(awk -v s="$SUMJOIN" -v v="${QREALJOIN[i]}" 'BEGIN{print s+v}')"
    fi
    [ "${QRATIOM[i]}" = "NA" ] && continue
    case "${QREG[i]}" in
        No)  NNO=$((NNO+1));   SUMNO="$(awk -v s="$SUMNO" -v r="${QRATIOM[i]}" 'BEGIN{print s+r}')";;
        Yes) NYES=$((NYES+1)); SUMYES="$(awk -v s="$SUMYES" -v r="${QRATIOM[i]}" 'BEGIN{print s+r}')";;
    esac
    case "${QSELECTED[i]}" in
        0) NBASELINE=$((NBASELINE+1)); SUMBASELINE="$(awk -v s="$SUMBASELINE" -v r="${QRATIOM[i]}" 'BEGIN{print s+r}')";;
        1) NOUTERYAN=$((NOUTERYAN+1)); SUMOUTERYAN="$(awk -v s="$SUMOUTERYAN" -v r="${QRATIOM[i]}" 'BEGIN{print s+r}')";;
    esac
done
NSKIP=$((QN-NCORRECT))
MNO="$(awk -v s="$SUMNO" -v n="$NNO" 'BEGIN{print (n? s/n : "-")}')"
MYES="$(awk -v s="$SUMYES" -v n="$NYES" 'BEGIN{print (n? s/n : "-")}')"
MBASELINE="$(awk -v s="$SUMBASELINE" -v n="$NBASELINE" 'BEGIN{print (n? s/n : "-")}')"
MOUTERYAN="$(awk -v s="$SUMOUTERYAN" -v n="$NOUTERYAN" 'BEGIN{print (n? s/n : "-")}')"
MR1="$(awk -v s="$SUMR1" -v n="$NPHASE" 'BEGIN{print (n? s/n : "-")}')"
MR2="$(awk -v s="$SUMR2" -v n="$NPHASE" 'BEGIN{print (n? s/n : "-")}')"
MJOIN="$(awk -v s="$SUMJOIN" -v n="$NPHASE" 'BEGIN{print (n? s/n : "-")}')"
{
    echo
    echo "============================== SUMMARY ================================"
    echo "queries=$QN  correct=$NCORRECT  incorrect/skipped=$NSKIP  timed=$NTIMED"
    echo "kernel (correct queries): bitmap=$NKBM  hash=$NKHASH  mixed=$NKMIX"
    [ "$NRETRY" -gt 0 ] && echo "retry pass: $NRETRY timed-out query(ies) re-run at ${RETRY_TO}s — $NRECOVERED now fully timed, $((NRETRY-NRECOVERED)) still timing out / partial (see retry rows above)"
    echo "threads: single=1, multi=${OY_THREADS}"
    echo "OuterYan decisions: same-grouping=$NSAME  changed-rejected=$NREJECT  selected=$NSELECTED  unknown=$NDECISION_UNKNOWN  cost-gate-applied=$NGATE_APPLIED"
    echo "speed-up by outer_reordered (reorder CSV compatibility column):"
    echo "  No:  n=$NNO  mean speed-up(TM)=$MNO"
    echo "  Yes: n=$NYES  mean speed-up(TM)=$MYES"
    echo "speed-up by outer_yan_selected:"
    echo "  DuckDB baseline: n=$NBASELINE  mean speed-up(TM)=$MBASELINE"
    echo "  OuterYan:        n=$NOUTERYAN  mean speed-up(TM)=$MOUTERYAN"
    echo "categorized operator elapsed seconds (n=$NPHASE profiled ON runs, threads=1; not complete phase wall time):"
    echo "  round 1 semi-join: sum=$SUMR1  mean=$MR1"
    echo "  round 2 semi-join: sum=$SUMR2  mean=$MR2"
    echo "  real joins:         sum=$SUMJOIN  mean=$MJOIN"
} >> "$OUT"

echo "Results written to $OUT"
echo "CSV written to $CSV_OUT"
