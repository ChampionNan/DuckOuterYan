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
#      (not-run | bitmap(b=N,h=0) | hash(b=0,h=N) | mixed(b=N,h=M) |
#      none(b=0,h=0)), from the DUCKDB_SJ_KERNEL_TRACE diagnostic.
#   4. TIMING — unprofiled OFF/ON medians at the selected multi-thread count.
#   5. PROFILE — separate native ON phase samples for OuterYan-selected queries.
# The default run uses 32 threads; explicit sweeps use separate result files.
# Profiling defaults to on; no single-thread executions are performed.
#
# USAGE: experiment_onoff.sh [options]
#   -b,--bin PATH     duckdb (default build/release/duckdb, else build/debug)
#   -n,--runs N       positive odd timed iterations per config (default 3)
#   -t,--timeout S    per-statement timeout sec (default 900). DuckDB enforces S
#                     on every query; the external timing-batch watchdog is
#                     (N+1)×S for 1 warm-up + N timed executions.
#      --only select|agg|pred|tpch|tpcds|job|graph|bench|all  query families
#                     (default all); bench = tpch+tpcds+job
#      --pattern GLOB  only queries whose label matches (default *)
#      --exclude GLOB  skip labels matching any '|'-separated glob
#      --limit N       cap number of queries (0 = no cap, default 0)
#      --query-list FILE  ordered corpus-relative SQL paths (requires --only all)
#      --capture-plans   save OFF/ON EXPLAIN, trace, and detailed cost artifacts
#      --threads LIST    thread counts, e.g. "16 32" or 16,32 (default 32)
#      --profile         collect separate ON phase profiles (default)
#      --no-profile      skip phase profiles; performance timing stays unprofiled
#   -o,--out FILE     results base (default experiment_onoff_<timestamp>_t<N>.txt)
# ============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Unified config: defines DUCKDB_BIN, GRAPH_DATASET, TPCH_SF/TPCDS_SF,
# OY_TIMEOUT_SECS, OY_RUNS.
. "$SCRIPT_DIR/configs.sh"
. "$SCRIPT_DIR/thread_sweep.sh"
. "$SCRIPT_DIR/phase_profile.sh"
[ -x "$DUCKDB_BIN" ] || export DUCKDB_BIN="$REPO_ROOT/build/debug/duckdb"
CORPUS="${OY_CORPUS:-$SCRIPT_DIR/outerjoin_query}"

RUNS="${OY_RUNS:-3}"; ONLY="all"; PATTERN="*"; EXCLUDE=""; LIMIT=0; OUT=""
QUERY_LIST=""; CAPTURE_PLANS="${OY_CAPTURE_PLANS:-0}"
PROFILE="${OY_PROFILE:-1}"
THREAD_COUNTS="${OY_THREAD_COUNTS:-$OY_THREADS}"
ORIGINAL_ARGS=("$@")
while [ $# -gt 0 ]; do case "$1" in
    -b|--bin) export DUCKDB_BIN="$2"; shift 2;;
    -n|--runs) RUNS="$2"; shift 2;;
    -t|--timeout) export OY_TIMEOUT_SECS="$2"; shift 2;;
    --only) ONLY="$2"; shift 2;;
    --pattern) PATTERN="$2"; shift 2;;
    --exclude) EXCLUDE="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    --query-list) QUERY_LIST="$2"; shift 2;;
    --capture-plans) CAPTURE_PLANS=1; shift;;
    --profile) PROFILE=1; shift;;
    --no-profile) PROFILE=0; shift;;
    --threads)
        [ $# -ge 2 ] || { echo "--threads requires a value" >&2; exit 2; }
        THREAD_COUNTS="$2"; shift 2;;
    -o|--out) OUT="$2"; shift 2;;
    -h|--help) sed -n '2,/^set /p' "${BASH_SOURCE[0]}"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 2;; esac; done
[ -z "$QUERY_LIST" ] || [ "$ONLY" = "all" ] || {
    echo "--query-list requires --only all" >&2; exit 2;
}
case "$RUNS" in
    ''|*[!0-9]*|0) echo "--runs must be a positive integer (got: $RUNS)" >&2; exit 2;;
esac
[ $((RUNS % 2)) -eq 1 ] || { echo "--runs must be odd so one real median execution is selected" >&2; exit 2; }
case "$PROFILE" in 0|1) ;; *) echo "OY_PROFILE must be 0 or 1" >&2; exit 2;; esac
oy_parse_thread_counts "$THREAD_COUNTS" || exit $?
# One experiment start timestamp, captured the moment this script begins (before
# the DB-build phase). Used for BOTH the .txt/.csv filenames AND the in-file
# header, so the txt, its corresponding csv, and the printed time all agree and
# all read as "when experiment_onoff.sh started". Single `date` call so the
# filename form and human form can never straddle a second boundary.
_now="$(date '+%Y%m%d_%H%M%S|%F %T')"
START_TS="${_now%%|*}"; START_HUMAN="${_now##*|}"
if [ "${#OY_THREAD_VALUES[@]}" -gt 1 ]; then
    sweep_out="${OUT:-$SCRIPT_DIR/results/experiment_onoff_${START_TS}.txt}"
    sweep_status=0
    sweep_pid=""
    oy_stop_sweep() {
        trap '' INT TERM
        if [ -n "$sweep_pid" ]; then
            kill -TERM "$sweep_pid" 2>/dev/null || true
            wait "$sweep_pid" 2>/dev/null || true
        fi
        exit "$1"
    }
    trap 'oy_stop_sweep 130' INT
    trap 'oy_stop_sweep 143' TERM
    for thread_count in "${OY_THREAD_VALUES[@]}"; do
        thread_out="${sweep_out%.txt}_t${thread_count}.txt"
        echo "--- Running multi-thread configuration: threads=$thread_count ---" >&2
        OY_THREADS="$thread_count" OY_THREAD_COUNTS="$thread_count" \
            bash "$SCRIPT_DIR/experiment_onoff.sh" "${ORIGINAL_ARGS[@]}" \
            --threads "$thread_count" --out "$thread_out" &
        sweep_pid=$!
        wait "$sweep_pid"
        thread_status=$?
        sweep_pid=""
        case "$thread_status" in
            130|143) exit "$thread_status";;
            0) ;;
            *) sweep_status="$thread_status";;
        esac
    done
    exit "$sweep_status"
fi
export OY_THREADS="${OY_THREAD_VALUES[0]}"
_default_out="$SCRIPT_DIR/results/experiment_onoff_${START_TS}_t${OY_THREADS}.txt"
OUT="${OUT:-$_default_out}"
mkdir -p "$(dirname "$OUT")"
mkdir -p "$OY_TMPDIR" || { echo "Error: cannot create OY_TMPDIR: $OY_TMPDIR" >&2; exit 1; }
[ -w "$OY_TMPDIR" ] || { echo "Error: OY_TMPDIR is not writable: $OY_TMPDIR" >&2; exit 1; }
OY_TMP_FREE="$(df -Ph "$OY_TMPDIR" 2>/dev/null | awk 'NR==2 {print $4}')"
OY_TMP_MOUNT="$(df -Ph "$OY_TMPDIR" 2>/dev/null | awk 'NR==2 {print $NF}')"
OY_TMP_FREE="${OY_TMP_FREE:-unknown}"
OY_TMP_MOUNT="${OY_TMP_MOUNT:-unknown}"
OY_RUN_TMPDIR=""

[ -x "$DUCKDB_BIN" ] || { echo "Error: duckdb not executable: $DUCKDB_BIN" >&2; exit 1; }
case "$DUCKDB_BIN" in *debug*) echo "WARNING: timing a DEBUG build — directional only; pass --bin <release>." >&2;; esac

# ============================================================================
# BENCH LIBRARY (inlined from outer_yan_bench_lib.sh)
# ============================================================================
OY_OFF="SET disabled_optimizers TO 'outer_yan';"
OY_ON="SET disabled_optimizers TO '';"
: "${OY_TIMEOUT_SECS:=900}"
: "${OY_BATCH_GRACE_SECS:=30}"
case "$OY_TIMEOUT_SECS" in
    ''|*[!0-9]*) echo "--timeout must be a non-negative integer (got: $OY_TIMEOUT_SECS)" >&2; exit 2;;
esac
case "$OY_BATCH_GRACE_SECS" in
    ''|*[!0-9]*) echo "OY_BATCH_GRACE_SECS must be a non-negative integer" >&2; exit 2;;
esac
OY_TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
[ "${OY_TIMEOUT_SECS}" = "0" ] && OY_TIMEOUT_BIN=""
OY_QUERY_SEPARATOR="===================================================================================================="

# DuckDB enforces this limit independently for every statement. The external
# `timeout` remains a process watchdog and is scaled for multi-statement timing
# batches, but no single bare-query execution can consume that entire batch.
oy_statement_timeout_sql() {
    local seconds="$1"
    [ "$seconds" != "0" ] || return 0
    printf 'SET max_execution_time=%s;' "$(( seconds * 1000 ))"
}

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
    if [ "${BASH_SUBSHELL:-0}" -eq 0 ] && [ -n "${OY_RUN_TMPDIR:-}" ]; then
        case "$OY_RUN_TMPDIR" in
            "$OY_TMPDIR"/run_*) rm -rf "$OY_RUN_TMPDIR" ;;
        esac
    fi
}
trap '_oy_cleanup; exit 130' INT
trap '_oy_cleanup; exit 143' TERM
trap '_oy_cleanup' EXIT

OY_RUN_TMPDIR="$(mktemp -d "$OY_TMPDIR/run_${START_TS}.XXXXXX")" || {
    echo "Error: cannot create run temporary directory under $OY_TMPDIR" >&2
    exit 1
}
export TMPDIR="$OY_RUN_TMPDIR"

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
        "$OY_TIMEOUT_BIN" "$OY_TIMEOUT_SECS" "$DUCKDB_BIN" -no-init -bail "$@" <&0 &
    else
        "$DUCKDB_BIN" -no-init -bail "$@" <&0 &
    fi
    pid=$!
    OY_DUCK_PIDS+=("$pid")
    wait "$pid"; rc=$?
    _oy_untrack "$pid"
    return $rc
}

# --- the correctness atom ---------------------------------------------------
# Runs the SAME query with OuterYan OFF and ON against <db>, compares both
# result sets as order-independent multisets. Both optimizer configurations
# execute the bare query; sorting happens on the emitted CSV files so the
# correctness check cannot change the optimized plan.
# This is the hard PRE-CONDITION run before any timing: a query that is not
# verified here (mismatch / error / timeout) is NOT timed. Each OFF/ON bare-query
# process has the same fixed per-statement and external timeout.
# RETURNS: 0 PASS | 1 FAIL (rows differ) | 2 ERROR | 3 TIMEOUT.
oy_equiv_check() {
    local db="$1" label="$2" query="$3"
    local off on eoff eon esort sql roff=0 ron=0 rc=0 off_rows=0 on_rows=0
    off=$(mktemp); on=$(mktemp); eoff=$(mktemp); eon=$(mktemp); esort=$(mktemp); sql=$(mktemp)
    local prag="CALL disable_profiling();PRAGMA threads=${OY_THREADS};$(oy_statement_timeout_sql "$OY_TIMEOUT_SECS")"

    printf '%s\n%s\n%s;\n' "$prag" "$OY_OFF" "${query%;}" > "$sql"
    if oy_duck "$db" -csv -noheader < "$sql" > "$off" 2>"$eoff"; then roff=0; else roff=$?; fi
    if [ "$roff" -eq 124 ]; then
        echo "  TIMEOUT (${OY_TIMEOUT_SECS}s, off): $label"; rc=3
    elif [ "$roff" -ne 0 ] || grep -qE 'Error:' "$eoff"; then
        echo "  ERROR (off rc=$roff): $label"
        { grep -m1 -E 'Error:' "$eoff" || sed -n '1p' "$eoff"; } | sed 's/^/        /'
        rc=2
    else
        off_rows="$(wc -l < "$off" | tr -d ' ')"
        if ! LC_ALL=C sort -o "$off" "$off" 2>"$esort"; then
            echo "  ERROR (sort off): $label"
            sed -n '1p' "$esort" | sed 's/^/        /'
            rc=2
        fi
    fi

    if [ "$rc" -eq 0 ]; then
        printf '%s\n%s\n%s;\n' "$prag" "$OY_ON" "${query%;}" > "$sql"
        if oy_duck "$db" -csv -noheader < "$sql" > "$on" 2>"$eon"; then ron=0; else ron=$?; fi
        if [ "$ron" -eq 124 ]; then
            echo "  TIMEOUT (${OY_TIMEOUT_SECS}s, on): $label"; rc=3
        elif [ "$ron" -ne 0 ] || grep -qE 'Error:' "$eon"; then
            echo "  ERROR (on rc=$ron): $label"
            { grep -m1 -E 'Error:' "$eon" || sed -n '1p' "$eon"; } | sed 's/^/        /'
            rc=2
        else
            on_rows="$(wc -l < "$on" | tr -d ' ')"
            : > "$esort"
            if ! LC_ALL=C sort -o "$on" "$on" 2>"$esort"; then
                echo "  ERROR (sort on): $label"
                sed -n '1p' "$esort" | sed 's/^/        /'
                rc=2
            fi
        fi
    fi
    if [ "$rc" -ne 0 ]; then
        :
    elif diff -q "$off" "$on" >/dev/null; then
        echo "  equiv OK: $label ($off_rows rows)"; rc=0
    else
        echo "  NOT EQUIV: $label (off=$off_rows on=$on_rows)"
        diff "$off" "$on" | head -6 | sed 's/^/        /'; rc=1
    fi
    rm -f "$off" "$on" "$eoff" "$eon" "$esort" "$sql"
    return $rc
}

# --- timing -----------------------------------------------------------------
# oy_time_median: run ONE warm-up followed by $runs timed executions, all with the
# timer on, and return the median over the TIMED runs (the warm-up is NOT counted,
# so total executions = $runs + 1). A partial/error batch is rejected instead of
# mixing a different number of samples into the benchmark.
# Output: "median_time runs_used"  (runs_used = how many TIMED runs the median spans)
: "${OY_RUNS:=3}"

oy_time_median() {
    local db="$1" set_sql="$2" query="$3" runs="$4" threads="$5"
    local script i
    # Trash mode still executes the bare query and fully drains its result, but
    # avoids charging terminal/result formatting and output I/O to the CLI timer.
    # Each configuration uses a fresh CLI process with DuckDB profiling off.
    # This setup runs before `.timer on`, so it is not part of the measurement.
    script=".timer off"$'\n'".mode trash"$'\n'"CALL disable_profiling();"$'\n'"PRAGMA threads=${threads};$(oy_statement_timeout_sql "$OY_TIMEOUT_SECS")"$'\n'"${set_sql}"$'\n'
    # 1 warm-up run + $runs timed runs (timer on for all). The warm-up primes the
    # buffer pool and is excluded from the median.
    script+=".timer on"$'\n'
    script+="${query%;};"$'\n'                                   # warm-up (not counted)
    for ((i=0; i<runs; i++)); do script+="${query%;};"$'\n'; done
    local times sqlf rawf
    sqlf=$(mktemp) || { echo "NA 0"; return; }
    rawf=$(mktemp) || { rm -f "$sqlf"; echo "NA 0"; return; }
    printf '%s' "$script" > "$sqlf"
    # OY_TIMEOUT_SECS is the PER-QUERY limit. The batch runs $runs+1 executions
    # (1 warm-up + $runs timed) in one process under a single `timeout`, so scale
    # the budget to (runs+1) * per-query so every run gets its full limit. When
    # the global timeout is disabled (OY_TIMEOUT_BIN empty / secs=0) this is moot.
    local saved_to="$OY_TIMEOUT_SECS" duck_rc=0
    [ -n "$OY_TIMEOUT_BIN" ] && [ "$OY_TIMEOUT_SECS" != "0" ] \
        && OY_TIMEOUT_SECS=$(( OY_TIMEOUT_SECS * (runs + 1) + OY_BATCH_GRACE_SECS ))
    if oy_duck "$db" -noheader < "$sqlf" > "$rawf" 2>&1; then
        duck_rc=0
    else
        duck_rc=$?
    fi
    OY_TIMEOUT_SECS="$saved_to"
    # Run Times in EXECUTION order; the first entry is the warm-up.
    times="$(awk '/Run Time/{for(i=1;i<=NF;i++) if($i=="real") print $(i+1)}' "$rawf")"
    local completed
    completed="$(printf '%s\n' "$times" | awk 'NF {n++} END {print n+0}')"
    if [ "$duck_rc" -ne 0 ] || grep -qE 'Error:' "$rawf" || [ "$completed" -ne $((runs + 1)) ]; then
        rm -f "$sqlf" "$rawf"
        echo "NA 0"
        return
    fi
    rm -f "$sqlf" "$rawf"
    # Median over the timed runs after dropping the warm-up.
    echo "$times" | awk '
        { t[NR]=$1 }
        END {
            n=NR
            lo=2                                  # skip the warm-up
            m=0; for(k=lo;k<=n;k++) a[++m]=t[k]   # timed set, still in run order
            for(i=1;i<=m;i++) for(j=i+1;j<=m;j++) if(a[j]<a[i]){x=a[i];a[i]=a[j];a[j]=x}
            if(m%2==1) med=a[(m+1)/2]; else med=(a[m/2]+a[m/2+1])/2
            printf "%.9f %d", med, m
        }'
}

# --- OuterYan candidate decision --------------------------------------------
# OuterYan emits exactly one machine-readable record while optimizing EXPLAIN:
#   [OY_DECISION] selection_mode=GATED|FORCE_OUTERYAN|FORCE_OUTERYAN_DIAGNOSTIC \
#                 outer_reordered=0|1 cost_gate_applied=0|1 \
#                 outer_yan_selected=0|1 reason=UPPER_SNAKE_TOKEN \
#                 baseline_cost=N|NA candidate_join_cost=N|NA \
#                 semijoin_raw_cost=N|NA semijoin_cost_ratio=N|NA \
#                 weighted_semijoin_cost=N|NA candidate_total=N|NA \
#                 cost_ratio_limit=N|NA baseline_threshold=N|NA \
#                 round1_build=N|NA round1_probe=N|NA \
#                 round2_build=N|NA round2_probe=N|NA \
#                 round1_pairs=N|NA round1_filters=N|NA \
#                 round2_pairs=N|NA round2_filters=N|NA \
#                 default_filter_upper_bound_checked=0|1 \
#                 default_filter_upper_bound_selected=0|1 \
#                 full_reduction_cardinality_lower_bound_applied=0|1 \
#                 uncertain_filter_amplification_guard=0|1 \
#                 stretch_cost_gate_eligible=0|1 \
#                 stretch_cost_gate_selected=0|1 \
#                 baseline_join_input_rows=N|NA \
#                 candidate_join_input_rows=N|NA \
#                 candidate_to_baseline_join_input_ratio=N|NA \
#                 semijoin_retained_cardinality_ratio=N|NA \
#                 uncertain_filter_cardinality_amplification=N|NA
#
# Results are returned through globals so oy_duck runs in this shell and remains
# covered by the PID-tracking/interrupt cleanup above.
OY_DECISION_REORDERED="NA"
OY_DECISION_GATE="NA"
OY_DECISION_SELECTED="NA"
OY_DECISION_REASON="TRACE_MISSING"
OY_DECISION_FORMULA_ID="NA"
OY_DECISION_SELECTION_MODE="NA"
OY_DECISION_SELECTED_PLAN="NA"
OY_DECISION_BASELINE_PROVEN_EMPTY="NA"
OY_DECISION_RAW_COST_WINNER="NA"
OY_DECISION_GATE_RESULT="NA"
OY_DECISION_DEFAULT_FILTER_UPPER_CHECKED="NA"
OY_DECISION_DEFAULT_FILTER_UPPER_SELECTED="NA"
OY_DECISION_FULL_REDUCTION_LOWER_BOUND="NA"
OY_DECISION_UNCERTAIN_FILTER_GUARD="NA"
OY_DECISION_STRETCH_ELIGIBLE="NA"
OY_DECISION_STRETCH_SELECTED="NA"
OY_DECISION_SEMIJOIN_RETAINED_RATIO="NA"
OY_DECISION_UNCERTAIN_FILTER_AMPLIFICATION="NA"
OY_DECISION_BASELINE_COST="NA"
OY_DECISION_CANDIDATE_JOIN_COST="NA"
OY_DECISION_BASELINE_JOIN_INPUT_ROWS="NA"
OY_DECISION_CANDIDATE_JOIN_INPUT_ROWS="NA"
OY_DECISION_JOIN_INPUT_RATIO="NA"
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
OY_DECISION_ROUND1_PAIRS="NA"
OY_DECISION_ROUND1_FILTERS="NA"
OY_DECISION_ROUND2_PAIRS="NA"
OY_DECISION_ROUND2_FILTERS="NA"
OY_DECISION_RAW_COST_DELTA="NA"
OY_DECISION_RAW_COST_RATIO="NA"
OY_DECISION_GATE_LHS="NA"
OY_DECISION_GATE_RHS="NA"
OY_DECISION_GATE_MARGIN="NA"
OY_DECISION_INNER_WEIGHT="NA"
OY_DECISION_UNMATCHED_LEFT_WEIGHT="NA"
OY_DECISION_UNMATCHED_RIGHT_WEIGHT="NA"
OY_DECISION_SJ_MATERIALIZE_WEIGHT="NA"
OY_DECISION_SJ_FILTER_BUILD_WEIGHT="NA"
OY_DECISION_SJ_REPLAY_WEIGHT="NA"
OY_DECISION_SJ_LOOKUP_WEIGHT="NA"
OY_DECISION_SJ_EMIT_WEIGHT="NA"

oy_record_value() {
    local record="$1" key="$2" token
    for token in $record; do
        case "$token" in
            "$key="*) printf '%s' "${token#*=}"; return;;
        esac
    done
    printf 'NA'
}

oy_reset_decision() {
    OY_DECISION_FORMULA_ID="NA"
    OY_DECISION_SELECTION_MODE="NA"
    OY_DECISION_SELECTED_PLAN="NA"
    OY_DECISION_REORDERED="NA"
    OY_DECISION_GATE="NA"
    OY_DECISION_SELECTED="NA"
    OY_DECISION_BASELINE_PROVEN_EMPTY="NA"
    OY_DECISION_REASON="TRACE_MISSING"
    OY_DECISION_RAW_COST_WINNER="NA"
    OY_DECISION_GATE_RESULT="NA"
    OY_DECISION_DEFAULT_FILTER_UPPER_CHECKED="NA"
    OY_DECISION_DEFAULT_FILTER_UPPER_SELECTED="NA"
    OY_DECISION_FULL_REDUCTION_LOWER_BOUND="NA"
    OY_DECISION_UNCERTAIN_FILTER_GUARD="NA"
    OY_DECISION_STRETCH_ELIGIBLE="NA"
    OY_DECISION_STRETCH_SELECTED="NA"
    OY_DECISION_SEMIJOIN_RETAINED_RATIO="NA"
    OY_DECISION_UNCERTAIN_FILTER_AMPLIFICATION="NA"
    OY_DECISION_BASELINE_COST="NA"
    OY_DECISION_CANDIDATE_JOIN_COST="NA"
    OY_DECISION_BASELINE_JOIN_INPUT_ROWS="NA"
    OY_DECISION_CANDIDATE_JOIN_INPUT_ROWS="NA"
    OY_DECISION_JOIN_INPUT_RATIO="NA"
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
    OY_DECISION_ROUND1_PAIRS="NA"
    OY_DECISION_ROUND1_FILTERS="NA"
    OY_DECISION_ROUND2_PAIRS="NA"
    OY_DECISION_ROUND2_FILTERS="NA"
    OY_DECISION_RAW_COST_DELTA="NA"
    OY_DECISION_RAW_COST_RATIO="NA"
    OY_DECISION_GATE_LHS="NA"
    OY_DECISION_GATE_RHS="NA"
    OY_DECISION_GATE_MARGIN="NA"
    OY_DECISION_INNER_WEIGHT="NA"
    OY_DECISION_UNMATCHED_LEFT_WEIGHT="NA"
    OY_DECISION_UNMATCHED_RIGHT_WEIGHT="NA"
    OY_DECISION_SJ_MATERIALIZE_WEIGHT="NA"
    OY_DECISION_SJ_FILTER_BUILD_WEIGHT="NA"
    OY_DECISION_SJ_REPLAY_WEIGHT="NA"
    OY_DECISION_SJ_LOOKUP_WEIGHT="NA"
    OY_DECISION_SJ_EMIT_WEIGHT="NA"
}

oy_decision() {
    local db="$1" query="$2" trace_dest="${3:-}" cost_dest="${4:-}"
    local sqlf tracef rc record
    local trace_was_set trace_saved
    sqlf=$(mktemp); tracef=$(mktemp)
    printf '%s\n%s\nEXPLAIN (FORMAT json) %s;\n' \
        "CALL disable_profiling();PRAGMA threads=${OY_THREADS};$(oy_statement_timeout_sql "$OY_TIMEOUT_SECS")" \
        "$OY_ON" "${query%;}" > "$sqlf"

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

    record="$(grep '^\[OY_DECISION\][[:space:]]' "$tracef" | tail -1)"
    oy_reset_decision
    [ "$rc" -eq 0 ] || OY_DECISION_REASON="TRACE_ERROR"
    if [ -n "$record" ]; then
        OY_DECISION_FORMULA_ID="$(oy_record_value "$record" formula_id)"
        OY_DECISION_SELECTION_MODE="$(oy_record_value "$record" selection_mode)"
        OY_DECISION_SELECTED_PLAN="$(oy_record_value "$record" selected_plan)"
        OY_DECISION_REORDERED="$(oy_record_value "$record" outer_reordered)"
        OY_DECISION_GATE="$(oy_record_value "$record" cost_gate_applied)"
        OY_DECISION_SELECTED="$(oy_record_value "$record" outer_yan_selected)"
        OY_DECISION_BASELINE_PROVEN_EMPTY="$(oy_record_value "$record" baseline_proven_empty)"
        OY_DECISION_REASON="$(oy_record_value "$record" reason)"
        OY_DECISION_RAW_COST_WINNER="$(oy_record_value "$record" raw_cost_winner)"
        OY_DECISION_GATE_RESULT="$(oy_record_value "$record" gate_result)"
        OY_DECISION_DEFAULT_FILTER_UPPER_CHECKED="$(oy_record_value "$record" default_filter_upper_bound_checked)"
        OY_DECISION_DEFAULT_FILTER_UPPER_SELECTED="$(oy_record_value "$record" default_filter_upper_bound_selected)"
        OY_DECISION_FULL_REDUCTION_LOWER_BOUND="$(oy_record_value "$record" full_reduction_cardinality_lower_bound_applied)"
        OY_DECISION_UNCERTAIN_FILTER_GUARD="$(oy_record_value "$record" uncertain_filter_amplification_guard)"
        OY_DECISION_STRETCH_ELIGIBLE="$(oy_record_value "$record" stretch_cost_gate_eligible)"
        OY_DECISION_STRETCH_SELECTED="$(oy_record_value "$record" stretch_cost_gate_selected)"
        OY_DECISION_SEMIJOIN_RETAINED_RATIO="$(oy_record_value "$record" semijoin_retained_cardinality_ratio)"
        OY_DECISION_UNCERTAIN_FILTER_AMPLIFICATION="$(oy_record_value "$record" uncertain_filter_cardinality_amplification)"
        OY_DECISION_BASELINE_COST="$(oy_record_value "$record" baseline_cost)"
        OY_DECISION_CANDIDATE_JOIN_COST="$(oy_record_value "$record" candidate_join_cost)"
        OY_DECISION_BASELINE_JOIN_INPUT_ROWS="$(oy_record_value "$record" baseline_join_input_rows)"
        OY_DECISION_CANDIDATE_JOIN_INPUT_ROWS="$(oy_record_value "$record" candidate_join_input_rows)"
        OY_DECISION_JOIN_INPUT_RATIO="$(oy_record_value "$record" candidate_to_baseline_join_input_ratio)"
        OY_DECISION_SEMIJOIN_RAW_COST="$(oy_record_value "$record" semijoin_raw_cost)"
        OY_DECISION_SEMIJOIN_COST_RATIO="$(oy_record_value "$record" semijoin_cost_ratio)"
        OY_DECISION_WEIGHTED_SEMIJOIN_COST="$(oy_record_value "$record" weighted_semijoin_cost)"
        OY_DECISION_CANDIDATE_TOTAL="$(oy_record_value "$record" candidate_total)"
        OY_DECISION_COST_RATIO_LIMIT="$(oy_record_value "$record" cost_ratio_limit)"
        OY_DECISION_BASELINE_THRESHOLD="$(oy_record_value "$record" baseline_threshold)"
        OY_DECISION_ROUND1_BUILD="$(oy_record_value "$record" round1_build)"
        OY_DECISION_ROUND1_PROBE="$(oy_record_value "$record" round1_probe)"
        OY_DECISION_ROUND2_BUILD="$(oy_record_value "$record" round2_build)"
        OY_DECISION_ROUND2_PROBE="$(oy_record_value "$record" round2_probe)"
        OY_DECISION_ROUND1_PAIRS="$(oy_record_value "$record" round1_pairs)"
        OY_DECISION_ROUND1_FILTERS="$(oy_record_value "$record" round1_filters)"
        OY_DECISION_ROUND2_PAIRS="$(oy_record_value "$record" round2_pairs)"
        OY_DECISION_ROUND2_FILTERS="$(oy_record_value "$record" round2_filters)"
        OY_DECISION_RAW_COST_DELTA="$(oy_record_value "$record" raw_cost_delta)"
        OY_DECISION_RAW_COST_RATIO="$(oy_record_value "$record" raw_cost_ratio)"
        OY_DECISION_GATE_LHS="$(oy_record_value "$record" gate_lhs)"
        OY_DECISION_GATE_RHS="$(oy_record_value "$record" gate_rhs)"
        OY_DECISION_GATE_MARGIN="$(oy_record_value "$record" gate_margin)"
        OY_DECISION_INNER_WEIGHT="$(oy_record_value "$record" inner_output_weight)"
        OY_DECISION_UNMATCHED_LEFT_WEIGHT="$(oy_record_value "$record" unmatched_left_weight)"
        OY_DECISION_UNMATCHED_RIGHT_WEIGHT="$(oy_record_value "$record" unmatched_right_weight)"
        OY_DECISION_SJ_MATERIALIZE_WEIGHT="$(oy_record_value "$record" semijoin_materialize_weight)"
        OY_DECISION_SJ_FILTER_BUILD_WEIGHT="$(oy_record_value "$record" semijoin_filter_build_weight)"
        OY_DECISION_SJ_REPLAY_WEIGHT="$(oy_record_value "$record" semijoin_replay_weight)"
        OY_DECISION_SJ_LOOKUP_WEIGHT="$(oy_record_value "$record" semijoin_probe_lookup_weight)"
        OY_DECISION_SJ_EMIT_WEIGHT="$(oy_record_value "$record" semijoin_probe_emit_weight)"
        case "$OY_DECISION_SELECTED_PLAN:$OY_DECISION_REORDERED:$OY_DECISION_GATE:$OY_DECISION_SELECTED:$OY_DECISION_BASELINE_PROVEN_EMPTY:$OY_DECISION_RAW_COST_WINNER:$OY_DECISION_GATE_RESULT" in
            DUCKDB:[01]:[01]:0:[01]:DUCKDB:*) ;;
            DUCKDB:[01]:[01]:0:[01]:OUTERYAN:*) ;;
            DUCKDB:[01]:[01]:0:[01]:EQUAL:*) ;;
            DUCKDB:[01]:[01]:0:[01]:UNAVAILABLE:*) ;;
            OUTERYAN:[01]:[01]:1:[01]:DUCKDB:*) ;;
            OUTERYAN:[01]:[01]:1:[01]:OUTERYAN:*) ;;
            OUTERYAN:[01]:[01]:1:[01]:EQUAL:*) ;;
            *) OY_DECISION_REASON="TRACE_INVALID";;
        esac
        case "$OY_DECISION_DEFAULT_FILTER_UPPER_CHECKED:$OY_DECISION_DEFAULT_FILTER_UPPER_SELECTED:$OY_DECISION_FULL_REDUCTION_LOWER_BOUND:$OY_DECISION_UNCERTAIN_FILTER_GUARD:$OY_DECISION_STRETCH_ELIGIBLE:$OY_DECISION_STRETCH_SELECTED" in
            [01]:[01]:[01]:[01]:[01]:[01]) ;;
            *) OY_DECISION_REASON="TRACE_INVALID";;
        esac
        if [ "$OY_DECISION_DEFAULT_FILTER_UPPER_SELECTED" = 1 ] && \
           [ "$OY_DECISION_DEFAULT_FILTER_UPPER_CHECKED" != 1 ]; then
            OY_DECISION_REASON="TRACE_INVALID"
        fi
        if [ "$OY_DECISION_STRETCH_SELECTED" = 1 ]; then
            case "$OY_DECISION_STRETCH_ELIGIBLE:$OY_DECISION_SELECTED_PLAN:$OY_DECISION_SELECTED:$OY_DECISION_GATE_RESULT:$OY_DECISION_REASON" in
                1:OUTERYAN:1:PASS:COST_OUTERYAN_STRETCH) ;;
                *) OY_DECISION_REASON="TRACE_INVALID";;
            esac
        fi
    fi
    if [ -n "$trace_dest" ]; then
        cp "$tracef" "$trace_dest"
    fi
    if [ -n "$cost_dest" ]; then
        awk '/^\[OY_(JOIN_COST|JOIN_COST_TOTAL|SJ_COST|DECISION)\]/ { print }' "$tracef" > "$cost_dest"
    fi
    rm -f "$sqlf" "$tracef"
}

oy_capture_plan() {
    local db="$1" setting="$2" query="$3" output="$4" sqlf rc
    sqlf=$(mktemp)
    printf "PRAGMA explain_output='all';\n%s\n%s\nEXPLAIN %s;\n" \
        "CALL disable_profiling();PRAGMA threads=${OY_THREADS};$(oy_statement_timeout_sql "$OY_TIMEOUT_SECS")" \
        "$setting" "${query%;}" > "$sqlf"
    oy_duck "$db" < "$sqlf" > "$output" 2>&1
    rc=$?
    rm -f "$sqlf"
    return "$rc"
}

# --- semi-join kernel classification (bitmap vs hash) -----------------------
# Like the join-order regime, the kernel each SJ filter commits to is a
# structural property of how OuterYan executed the query. The kind is decided at
# runtime (PhysicalSJBuild::Finalize, including the bitmap->hash overflow
# fallback), so we cannot read it from EXPLAIN — instead we run the query ONCE
# with OuterYan ON and the C++ kernel trace (env DUCKDB_SJ_KERNEL_TRACE) on, then
# count the per-filter "[SJ_KERNEL] BITMAP|HASH" lines it prints to stderr.
# Echoes: "<label>|b<N>h<M>|<reason-counts>|<status>". `none` means an
# OuterYan execution completed but finalized no SJ filter; `not-run` is used
# only when the trace execution itself failed.
oy_kernel() {
    local db="$1" query="$2" sqlf errf nbm nhash label rc
    local nforce nbudget nineligible noverflow reasons="" separator=""
    sqlf=$(mktemp); errf=$(mktemp)
    printf '%s\n%s\n%s\n' "CALL disable_profiling();PRAGMA threads=${OY_THREADS};$(oy_statement_timeout_sql "$OY_TIMEOUT_SECS")" \
        "$OY_ON" "${query%;};" > "$sqlf"
    # Scope the trace to this single run: export before, unset after, so the
    # timing/equivalence oy_duck calls never see the extra stderr.
    export DUCKDB_SJ_KERNEL_TRACE=1
    oy_duck "$db" -noheader < "$sqlf" >/dev/null 2>"$errf"
    rc=$?
    unset DUCKDB_SJ_KERNEL_TRACE
    nbm="$(grep -c '\[SJ_KERNEL\] BITMAP' "$errf")"
    nhash="$(grep -c '\[SJ_KERNEL\] HASH' "$errf")"
    nforce="$(grep -c '\[SJ_KERNEL\] HASH reason=force_hash' "$errf")"
    nbudget="$(grep -c '\[SJ_KERNEL\] HASH reason=budget0' "$errf")"
    nineligible="$(grep -c '\[SJ_KERNEL\] HASH reason=ineligible' "$errf")"
    noverflow="$(grep -c '\[SJ_KERNEL\] HASH reason=overflow' "$errf")"
    for reason_count in "force_hash:$nforce" "budget0:$nbudget" \
                        "ineligible:$nineligible" "overflow:$noverflow"; do
        [ "${reason_count##*:}" -gt 0 ] || continue
        reasons+="${separator}${reason_count}"
        separator=","
    done
    [ -n "$reasons" ] || reasons="-"
    rm -f "$sqlf" "$errf"
    if [ "$rc" -ne 0 ]; then
        echo "not-run|b0h0|$reasons|error"
        return
    fi
    if   [ "$nbm" -gt 0 ] && [ "$nhash" -gt 0 ]; then label="mixed"
    elif [ "$nbm" -gt 0 ]; then label="bitmap"
    elif [ "$nhash" -gt 0 ]; then label="hash"
    else label="none"; fi
    echo "$label|b${nbm}h${nhash}|$reasons|ok"
}

oy_kernel_display() {
    local label="$1" detail="$2" b h
    if [ "$label" = "not-run" ]; then
        printf 'not-run'
        return
    fi
    b="$(printf '%s' "$detail" | sed -nE 's/^b([0-9]+)h[0-9]+$/\1/p')"
    h="$(printf '%s' "$detail" | sed -nE 's/^b[0-9]+h([0-9]+)$/\1/p')"
    printf '%s(b=%s,h=%s)' "$label" "${b:-0}" "${h:-0}"
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

GRAPH_DB="${GRAPH_DB:-}"; TPCH_DB="${TPCH_DB:-$REPO_ROOT/tpch_db}"
TPCDS_DB="${TPCDS_DB:-$REPO_ROOT/tpcds_db}"
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
    if [ -f "$GRAPH_DB" ]; then
        :
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
LABELS=(); SQLS=(); DBS=(); QUERY_FAMILIES=(); SQL_PATHS=(); RELATION_COUNTS=()

# Corpus queries are deliberately flat: one FROM relation followed by explicit
# JOIN relations (no CTEs or subqueries). Count those SQL tokens instead of
# inferring depth from the label, whose convention differs across families.
oy_relation_count() {
    printf '%s\n' "$1" | awk '
        {
            sub(/--.*/, "")
            gsub(/[^[:alnum:]_]+/, " ")
            for (i = 1; i <= NF; i++) {
                token = tolower($i)
                if (token == "from" || token == "join") count++
            }
        }
        END { if (count > 0) print count; else print "-" }
    '
}

db_for_family() {
    case "$1" in
        graph) printf '%s' "$GRAPH_DB";;
        tpch)  printf '%s' "$TPCH_DB";;
        tpcds) printf '%s' "$TPCDS_DB";;
        job)   printf '%s' "$JOB_DB";;
        *) return 1;;
    esac
}

append_query() {
    local family="$1" rel="$2" fdb existing query_sql relation_count
    local full="$CORPUS/$rel"
    [ -f "$full" ] || { echo "Missing query: $rel" >&2; exit 2; }
    for existing in "${SQL_PATHS[@]:-}"; do
        [ "$existing" != "$rel" ] || { echo "Duplicate query in selection: $rel" >&2; exit 2; }
    done
    fdb="$(db_for_family "$family")" || { echo "Unknown query family: $family" >&2; exit 2; }
    [ -n "$fdb" ] && [ -f "$fdb" ] || { echo "Database unavailable for $rel: $fdb" >&2; exit 2; }
    query_sql="$(<"$full")"
    relation_count="$(oy_relation_count "$query_sql")"
    [ "$relation_count" != "-" ] || { echo "Could not count relations in $rel" >&2; exit 2; }
    LABELS+=("$(basename "$full" .sql)")
    SQLS+=("$query_sql")
    DBS+=("$fdb")
    QUERY_FAMILIES+=("$family")
    SQL_PATHS+=("$rel")
    RELATION_COUNTS+=("$relation_count")
}

if [ -n "$QUERY_LIST" ]; then
    [ -f "$QUERY_LIST" ] || { echo "Query list not found: $QUERY_LIST" >&2; exit 2; }
    rel=""
    while IFS= read -r rel || [ -n "$rel" ]; do
        rel="$(printf '%s' "$rel" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
        [ -n "$rel" ] || continue
        case "$rel" in \#*) continue;; esac
        case "$rel" in /*|../*|*/../*|*/..) echo "Unsafe query-list path: $rel" >&2; exit 2;; esac
        family="${rel%%/*}"
        case "$family" in graph|tpch|tpcds|job) ;; *) echo "Unknown family in $rel" >&2; exit 2;; esac
        append_query "$family" "$rel"
        [ "$LIMIT" -gt 0 ] && [ "${#LABELS[@]}" -ge "$LIMIT" ] && break
    done < "$QUERY_LIST"
else
    for fam in $FAMS; do
        case "$fam" in
            graph)  dir="$CORPUS/graph";;
            tpch)   [ "$need_tpch"  = 1 ] || continue; dir="$CORPUS/tpch";;
            tpcds)  [ "$need_tpcds" = 1 ] || continue; dir="$CORPUS/tpcds";;
            job)    [ "$need_job"   = 1 ] || continue; dir="$CORPUS/job";;
        esac
        [ -d "$dir" ] || continue
        # Use a locale-independent filename order so repeated corpus runs visit
        # queries in exactly the same sequence on Linux and macOS.
        while IFS= read -r f; do
            case "$f" in *_off.sql) continue;; esac
            lbl="$(basename "$f" .sql)"
            case "$lbl" in $PATTERN) ;; *) continue;; esac
            if [ -n "$EXCLUDE" ]; then
                _skip=0; IFS='|' read -ra _ex <<< "$EXCLUDE"
                for _g in "${_ex[@]}"; do case "$lbl" in $_g) _skip=1; break;; esac; done
                [ "$_skip" = 1 ] && continue
            fi
            append_query "$fam" "$fam/$(basename "$f")"
            [ "$LIMIT" -gt 0 ] && [ "${#LABELS[@]}" -ge "$LIMIT" ] && break
        done < <(find "$dir" -maxdepth 1 -type f -name '*.sql' -print | LC_ALL=C sort)
        [ "$LIMIT" -gt 0 ] && [ "${#LABELS[@]}" -ge "$LIMIT" ] && break
    done
fi
[ "${#LABELS[@]}" -gt 0 ] || { echo "No corpus queries matched (only=$ONLY pattern=$PATTERN)" >&2; exit 1; }
SIZES="families=[$FAMS]  graph=$GRAPH_DATASET  tpch sf=$TPCH_SF  tpcds sf=$TPCDS_SF  job db=$JOB_DB"

# ============================================================================
# RUN: gate -> decision -> kernel/time, streaming to TXT/CSV
# ============================================================================
CSV_FINAL="${OUT%.txt}.csv"
CSV_ATTEMPTS="${OUT%.txt}.attempts.csv"
PLAN_DIR="${OUT%.txt}.plans"
[ "$CAPTURE_PLANS" = 1 ] && mkdir -p "$PLAN_DIR"
PROFILE_DIR="${OUT%.txt}.profiles"
if [ "$PROFILE" = 1 ]; then
    mkdir -p "$PROFILE_DIR" || { echo "Cannot create profile directory: $PROFILE_DIR" >&2; exit 1; }
    PROFILE_DIR="$(cd "$PROFILE_DIR" && pwd)"
fi

csv_escape() {
    local value="$1"
    value="${value//\"/\"\"}"
    printf '"%s"' "$value"
}

csv_row() {
    local output="$1" value separator=""
    shift
    for value in "$@"; do
        printf '%s' "$separator" >> "$output"
        csv_escape "$value" >> "$output"
        separator=','
    done
    printf '\n' >> "$output"
}

csv_result_row() {
    csv_row "$CSV_FINAL" "$@"
    csv_row "$CSV_ATTEMPTS" "$@"
}

CSV_HEADER=(
    query family sql_path relation_count reorder outer_reordered cost_gate_applied outer_yan_selected selected_plan
    baseline_proven_empty decision_reason formula_id selection_mode raw_cost_winner gate_result
    default_filter_upper_bound_checked default_filter_upper_bound_selected
    full_reduction_cardinality_lower_bound_applied uncertain_filter_amplification_guard
    stretch_cost_gate_eligible stretch_cost_gate_selected
    baseline_join_input_rows candidate_join_input_rows candidate_to_baseline_join_input_ratio
    semijoin_retained_cardinality_ratio
    uncertain_filter_cardinality_amplification
    baseline_cost candidate_join_cost semijoin_raw_cost semijoin_cost_ratio weighted_semijoin_cost
    candidate_total cost_ratio_limit baseline_threshold round1_build round1_probe round2_build round2_probe
    round1_pairs round1_filters round2_pairs round2_filters
    raw_cost_delta raw_cost_ratio gate_lhs gate_rhs gate_margin
    inner_output_weight unmatched_left_weight unmatched_right_weight semijoin_materialize_weight
    semijoin_filter_build_weight semijoin_replay_weight semijoin_probe_lookup_weight semijoin_probe_emit_weight
    kernel kernel_detail kernel_hash_reasons correct note timing_threads tm_off tm_on tm_speedup
    rows effective_pass duckdb_plan enabled_plan trace_file cost_file
    profile_status profile_threads profile_round1_operator_s profile_round2_operator_s profile_round3_operator_s
    profile_round1_operator_count profile_round2_operator_count profile_round3_operator_count
    profile_total_time_s profile_cpu_time_s profile_round1_ratio profile_round2_ratio profile_total_sj_ratio
    profile_round3_ratio profile_other_elapsed_s profile_other_ratio profile_timed_samples profile_directory
)
: > "$CSV_FINAL"
: > "$CSV_ATTEMPTS"
csv_row "$CSV_FINAL" "${CSV_HEADER[@]}"
csv_row "$CSV_ATTEMPTS" "${CSV_HEADER[@]}"

# Header (truncate + write)
{
    echo "# OuterYan on/off experiment   started $START_HUMAN"
    echo "# binary : $DUCKDB_BIN"
    echo "# corpus : $ONLY  (pattern=$PATTERN limit=$LIMIT) — ${#LABELS[@]} queries from $CORPUS"
    echo "# relations: counted from FROM/JOIN tokens in each flat bare query"
    echo "# tables : $SIZES"
    echo "# timing : threads=${OY_THREADS}, median of ${RUNS} runs per config (1 warm-up + ${RUNS} timed)"
    echo "# overhead: correctness, diagnostics and TM timing disable profiling; separate ON phase batch enabled=$PROFILE"
    echo "# phases : OuterYan-selected only, threads=${OY_THREADS}, 1 warm-up + ${RUNS} samples; whole tuple at median profile latency"
    echo "#          Round 1/2/3 + OtherCPU = aggregate CPU-Time, not wall-clock Total-Time; raw JSON: $PROFILE_DIR"
    echo "# timeout: hard ${OY_TIMEOUT_SECS}s/statement (DuckDB max_execution_time); external single-query watchdog=${OY_TIMEOUT_SECS}s, timing-batch watchdog=$(( OY_TIMEOUT_SECS * (RUNS + 1) + OY_BATCH_GRACE_SECS ))s; no retry"
    echo "# temp    : base=$OY_TMPDIR run=$OY_RUN_TMPDIR ($OY_TMP_FREE available on $OY_TMP_MOUNT)"
    echo "# correct: ON result multiset == OFF result; only correct queries are timed"
    echo "# formula : candidate_total = candidate_join_cost + semijoin_cost_ratio * semijoin_raw_cost"
    echo "# gate    : candidate_total <= cost_ratio_limit * baseline_cost"
    echo "# compare : raw_cost_winner compares candidate_total directly with baseline_cost"
    echo "# capture : plans=$CAPTURE_PLANS directory=$PLAN_DIR"
    echo
    echo "===================== PER-QUERY RESULT BLOCKS ========================="
    echo "# Columns: TM = unprofiled wall-clock timing at threads=${OY_THREADS}"
    echo "# Each query has exactly two lines after a full-width separator:"
    echo "#   line 1 = query/result, selected plan, kernel, thread count, and TM"
    echo "#   line 2 = decision, cost/gate inputs, weights, notices, and artifacts"
    echo "#   kernel = not-run | bitmap(b=N,h=0) | hash(b=0,h=N) | mixed(b=N,h=M) | none(b=0,h=0)"
} > "$OUT"

# Per-query state arrays (index = query #). Written by process_one and read by
# the final summary.
QLBL=(); QNREL=(); QCORRECT=(); QNOTE=(); QROWS=(); QREG=()
QDB=(); QSQL=(); QFAMILY=(); QPATH=(); QKER=(); QKDETAIL=(); QKREASONS=()
QREORDERED=(); QGATE=(); QSELECTED=(); QDECISION=()
QFORMULA=(); QSELECTION_MODE=(); QSELECTED_PLAN=(); QPROVEN_EMPTY=(); QRAW_WINNER=(); QGATE_RESULT=()
QFULL_REDUCTION_LOWER_BOUND=(); QSTRETCH_ELIGIBLE=(); QSTRETCH_SELECTED=()
QBASELINE_JOIN_INPUT_ROWS=(); QCANDIDATE_JOIN_INPUT_ROWS=(); QJOIN_INPUT_RATIO=()
QBASELINE_COST=(); QCANDIDATE_JOIN_COST=(); QSEMIJOIN_RAW_COST=(); QSEMIJOIN_COST_RATIO=()
QWEIGHTED_SEMIJOIN_COST=(); QCANDIDATE_TOTAL=()
QCOST_RATIO_LIMIT=(); QBASELINE_THRESHOLD=()
QROUND1_BUILD=(); QROUND1_PROBE=(); QROUND2_BUILD=(); QROUND2_PROBE=()
QROUND1_PAIRS=(); QROUND1_FILTERS=(); QROUND2_PAIRS=(); QROUND2_FILTERS=()
QRAW_DELTA=(); QRAW_RATIO=(); QGATE_LHS=(); QGATE_RHS=(); QGATE_MARGIN=()
QINNER_WEIGHT=(); QUNMATCHED_LEFT_WEIGHT=(); QUNMATCHED_RIGHT_WEIGHT=()
QSJ_MATERIALIZE_WEIGHT=(); QSJ_FILTER_BUILD_WEIGHT=(); QSJ_REPLAY_WEIGHT=()
QSJ_LOOKUP_WEIGHT=(); QSJ_EMIT_WEIGHT=()
QOFFM=(); QONM=(); QRATIOM=()
QEFFECTIVE_PASS=(); QDUCKDB_PLAN=(); QENABLED_PLAN=(); QTRACE_FILE=(); QCOST_FILE=()

PASS="main"            # Retained in CSV/artifact names for output compatibility.

# process_one <i> — run the full pipeline for query i (gate -> decision -> kernel
# -> timing -> optional profile) under the fixed $OY_TIMEOUT_SECS, store the result in the Q*
# arrays at index i, and append one row to TXT and CSV.
process_one() {
    local i="$1"
    local id="${LABELS[i]}" sql="${SQLS[i]}" db="${DBS[i]}"
    local family="${QUERY_FAMILIES[i]}" sql_path="${SQL_PATHS[i]}"
    local nrel="${RELATION_COUNTS[i]}"
    local gate correct note rows
    gate="$(oy_equiv_check "$db" "$id" "$sql")"
    case "$gate" in
        *"equiv OK"*)  correct="TRUE";  note="OK";        rows="$(printf '%s' "$gate" | grep -oE '[0-9]+ rows' | grep -oE '[0-9]+')";;
        *"NOT EQUIV"*) correct="FALSE"; note="NOT-EQUIV"; rows="$(printf '%s' "$gate" | grep -oE 'off=[0-9]+ on=[0-9]+')";;
        *"TIMEOUT"*)   correct="FALSE"; note="TIMEOUT";   rows="-";;
        *)             correct="FALSE"; note="ERROR";     rows="-";;
    esac
    local reg="-" outer_reordered="-" gate_applied="-" selected="-" decision="-"
    local formula_id="-" selection_mode="-" selected_plan="-" proven_empty="-" raw_winner="-" gate_result="-"
    local default_filter_upper_checked="-" default_filter_upper_selected="-" uncertain_filter_guard="-"
    local full_reduction_lower_bound="-" stretch_eligible="-" stretch_selected="-"
    local baseline_join_input_rows="-" candidate_join_input_rows="-" join_input_ratio="-"
    local semijoin_retained_ratio="-" uncertain_filter_amplification="-"
    local baseline_cost="-" candidate_join_cost="-" semijoin_raw_cost="-"
    local semijoin_cost_ratio="-" weighted_semijoin_cost="-" candidate_total="-"
    local cost_ratio_limit="-" baseline_threshold="-"
    local round1_build="-" round1_probe="-" round2_build="-" round2_probe="-"
    local round1_pairs="-" round1_filters="-" round2_pairs="-" round2_filters="-"
    local raw_delta="-" raw_ratio="-" gate_lhs="-" gate_rhs="-" gate_margin="-"
    local inner_weight="-" unmatched_left_weight="-" unmatched_right_weight="-"
    local sj_materialize_weight="-" sj_filter_build_weight="-" sj_replay_weight="-"
    local sj_lookup_weight="-" sj_emit_weight="-"
    local ker="not-run" kdetail="b0h0" kreasons="-" kernel_status="not-run" kernel_display="not-run"
    local offm="-" onm="-" ratiom="-"
    local duckdb_plan="-" enabled_plan="-" trace_file="-" cost_file="-"
    local profile_status="disabled" profile_threads="-" profile_directory="-"
    local r1sj="NA" r2sj="NA" realjoin="NA" profile_wall="NA" profile_cpu="NA"
    local r1ratio="NA" r2ratio="NA" sjratio="NA" realjoin_ratio="NA" other="NA" other_ratio="NA"
    local r1_operators="NA" r2_operators="NA" realjoin_operators="NA" profile_samples="NA"
    [ "$PROFILE" = 0 ] || profile_status="not-correct"
    if [ "$correct" = "TRUE" ]; then
        if [ "$CAPTURE_PLANS" = 1 ]; then
            local artifact_stem="$PLAN_DIR/${family}__${id}.${PASS}"
            duckdb_plan="${artifact_stem}.duckdb.plan.txt"
            enabled_plan="${artifact_stem}.enabled.plan.txt"
            trace_file="${artifact_stem}.trace.txt"
            cost_file="${artifact_stem}.cost.txt"
        fi
        oy_decision "$db" "$sql" \
            "$([ "$CAPTURE_PLANS" = 1 ] && printf '%s' "$trace_file")" \
            "$([ "$CAPTURE_PLANS" = 1 ] && printf '%s' "$cost_file")"
        formula_id="$OY_DECISION_FORMULA_ID"
        selection_mode="$OY_DECISION_SELECTION_MODE"
        selected_plan="$OY_DECISION_SELECTED_PLAN"
        outer_reordered="$OY_DECISION_REORDERED"
        gate_applied="$OY_DECISION_GATE"
        selected="$OY_DECISION_SELECTED"
        proven_empty="$OY_DECISION_BASELINE_PROVEN_EMPTY"
        decision="$OY_DECISION_REASON"
        raw_winner="$OY_DECISION_RAW_COST_WINNER"
        gate_result="$OY_DECISION_GATE_RESULT"
        default_filter_upper_checked="$OY_DECISION_DEFAULT_FILTER_UPPER_CHECKED"
        default_filter_upper_selected="$OY_DECISION_DEFAULT_FILTER_UPPER_SELECTED"
        full_reduction_lower_bound="$OY_DECISION_FULL_REDUCTION_LOWER_BOUND"
        uncertain_filter_guard="$OY_DECISION_UNCERTAIN_FILTER_GUARD"
        stretch_eligible="$OY_DECISION_STRETCH_ELIGIBLE"
        stretch_selected="$OY_DECISION_STRETCH_SELECTED"
        semijoin_retained_ratio="$OY_DECISION_SEMIJOIN_RETAINED_RATIO"
        uncertain_filter_amplification="$OY_DECISION_UNCERTAIN_FILTER_AMPLIFICATION"
        baseline_cost="$OY_DECISION_BASELINE_COST"
        candidate_join_cost="$OY_DECISION_CANDIDATE_JOIN_COST"
        baseline_join_input_rows="$OY_DECISION_BASELINE_JOIN_INPUT_ROWS"
        candidate_join_input_rows="$OY_DECISION_CANDIDATE_JOIN_INPUT_ROWS"
        join_input_ratio="$OY_DECISION_JOIN_INPUT_RATIO"
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
        round1_pairs="$OY_DECISION_ROUND1_PAIRS"
        round1_filters="$OY_DECISION_ROUND1_FILTERS"
        round2_pairs="$OY_DECISION_ROUND2_PAIRS"
        round2_filters="$OY_DECISION_ROUND2_FILTERS"
        raw_delta="$OY_DECISION_RAW_COST_DELTA"
        raw_ratio="$OY_DECISION_RAW_COST_RATIO"
        gate_lhs="$OY_DECISION_GATE_LHS"
        gate_rhs="$OY_DECISION_GATE_RHS"
        gate_margin="$OY_DECISION_GATE_MARGIN"
        inner_weight="$OY_DECISION_INNER_WEIGHT"
        unmatched_left_weight="$OY_DECISION_UNMATCHED_LEFT_WEIGHT"
        unmatched_right_weight="$OY_DECISION_UNMATCHED_RIGHT_WEIGHT"
        sj_materialize_weight="$OY_DECISION_SJ_MATERIALIZE_WEIGHT"
        sj_filter_build_weight="$OY_DECISION_SJ_FILTER_BUILD_WEIGHT"
        sj_replay_weight="$OY_DECISION_SJ_REPLAY_WEIGHT"
        sj_lookup_weight="$OY_DECISION_SJ_LOOKUP_WEIGHT"
        sj_emit_weight="$OY_DECISION_SJ_EMIT_WEIGHT"
        case "$outer_reordered" in 1) reg="Yes";; 0) reg="No";; *) reg="-";; esac
        case "$selected_plan:$selected" in
            DUCKDB:0|OUTERYAN:1) ;;
            *) note="TRACE-INCONSISTENT";;
        esac
        if [ "$CAPTURE_PLANS" = 1 ]; then
            oy_capture_plan "$db" "$OY_OFF" "$sql" "$duckdb_plan" || note="${note};OFF-PLAN-ERROR"
            oy_capture_plan "$db" "$OY_ON" "$sql" "$enabled_plan" || note="${note};ON-PLAN-ERROR"
        fi
        if [ "$selected_plan" = "OUTERYAN" ]; then
            local kraw
            kraw="$(oy_kernel "$db" "$sql")"
            IFS='|' read -r ker kdetail kreasons kernel_status <<< "$kraw"
            if [ "$kernel_status" != "ok" ]; then
                note="${note};KERNEL-TRACE-ERROR"
            fi
        else
            ker="not-run"; kdetail="b0h0"; kreasons="-"; kernel_status="not-run"
        fi
        kernel_display="$(oy_kernel_display "$ker" "$kdetail")"
        local local_rom local_rnm
        local_rom="$(oy_time_median "$db" "$OY_OFF" "$sql" "$RUNS" "${OY_THREADS}")"
        local_rnm="$(oy_time_median "$db" "$OY_ON"  "$sql" "$RUNS" "${OY_THREADS}")"
        offm="$(echo "$local_rom" | awk '{print $1}')"; onm="$(echo "$local_rnm" | awk '{print $1}')"
        ratiom="$(awk -v off="$offm" -v on="$onm" 'BEGIN{ if(off!="NA"&&on!="NA"&&on+0>0) printf "%.3f", off/on; else print "NA" }')"
        if [ "$PROFILE" = 1 ]; then
            profile_status="not-selected"
            if [ "$selected_plan" = "OUTERYAN" ]; then
                local profile_result profile_rc=0 praw
                local -a profile_fields=()
                profile_threads="$OY_THREADS"
                profile_status="ERROR"
                profile_directory="$(mktemp -d "$PROFILE_DIR/${family}__${id}.XXXXXX")" || profile_rc=1
                profile_result="$(mktemp)" || profile_rc=1
                if [ "$profile_rc" = 0 ]; then
                    # Direct call keeps DuckDB owned by this shell's PID tracker.
                    oy_phase_profile "$db" "$sql" "$OY_THREADS" "$RUNS" "$selected_plan" \
                        "$round1_pairs" "$round2_pairs" "$proven_empty" "$profile_directory" \
                        > "$profile_result" || profile_rc=$?
                    praw="$(< "$profile_result")"
                    read -r -a profile_fields <<< "$praw"
                    rm -f "$profile_result"
                fi
                if [ "$profile_rc" = 0 ] && [ "${#profile_fields[@]}" -eq 15 ] && \
                   [ "${profile_fields[3]}" != "NA" ]; then
                    read -r r1sj r2sj realjoin profile_wall profile_cpu r1ratio r2ratio sjratio \
                        realjoin_ratio other other_ratio r1_operators r2_operators realjoin_operators \
                        profile_samples <<< "$praw"
                    profile_status="OK"
                else
                    # Do not discard valid unprofiled timing pairs after a profile failure.
                    note="${note};PROFILE-ERROR"
                    echo "PROFILE-ERROR: $id; see ${profile_directory:-unavailable}/duckdb.log" >&2
                fi
            fi
        fi
    fi
    # Store final state for the summary.
    QLBL[$i]="$id"; QNREL[$i]="$nrel"; QCORRECT[$i]="$correct"; QNOTE[$i]="$note"; QROWS[$i]="$rows"
    QREG[$i]="$reg"; QDB[$i]="$db"; QSQL[$i]="$sql"; QFAMILY[$i]="$family"; QPATH[$i]="$sql_path"
    QKER[$i]="$ker"; QKDETAIL[$i]="$kdetail"; QKREASONS[$i]="$kreasons"
    QREORDERED[$i]="$outer_reordered"; QGATE[$i]="$gate_applied"; QSELECTED[$i]="$selected"; QDECISION[$i]="$decision"
    QFORMULA[$i]="$formula_id"; QSELECTION_MODE[$i]="$selection_mode"
    QSELECTED_PLAN[$i]="$selected_plan"; QPROVEN_EMPTY[$i]="$proven_empty"
    QRAW_WINNER[$i]="$raw_winner"; QGATE_RESULT[$i]="$gate_result"
    QFULL_REDUCTION_LOWER_BOUND[$i]="$full_reduction_lower_bound"
    QSTRETCH_ELIGIBLE[$i]="$stretch_eligible"; QSTRETCH_SELECTED[$i]="$stretch_selected"
    QBASELINE_JOIN_INPUT_ROWS[$i]="$baseline_join_input_rows"
    QCANDIDATE_JOIN_INPUT_ROWS[$i]="$candidate_join_input_rows"; QJOIN_INPUT_RATIO[$i]="$join_input_ratio"
    QBASELINE_COST[$i]="$baseline_cost"; QCANDIDATE_JOIN_COST[$i]="$candidate_join_cost"
    QSEMIJOIN_RAW_COST[$i]="$semijoin_raw_cost"; QSEMIJOIN_COST_RATIO[$i]="$semijoin_cost_ratio"
    QWEIGHTED_SEMIJOIN_COST[$i]="$weighted_semijoin_cost"; QCANDIDATE_TOTAL[$i]="$candidate_total"
    QCOST_RATIO_LIMIT[$i]="$cost_ratio_limit"; QBASELINE_THRESHOLD[$i]="$baseline_threshold"
    QROUND1_BUILD[$i]="$round1_build"; QROUND1_PROBE[$i]="$round1_probe"
    QROUND2_BUILD[$i]="$round2_build"; QROUND2_PROBE[$i]="$round2_probe"
    QROUND1_PAIRS[$i]="$round1_pairs"; QROUND1_FILTERS[$i]="$round1_filters"
    QROUND2_PAIRS[$i]="$round2_pairs"; QROUND2_FILTERS[$i]="$round2_filters"
    QRAW_DELTA[$i]="$raw_delta"; QRAW_RATIO[$i]="$raw_ratio"; QGATE_LHS[$i]="$gate_lhs"
    QGATE_RHS[$i]="$gate_rhs"; QGATE_MARGIN[$i]="$gate_margin"
    QINNER_WEIGHT[$i]="$inner_weight"; QUNMATCHED_LEFT_WEIGHT[$i]="$unmatched_left_weight"
    QUNMATCHED_RIGHT_WEIGHT[$i]="$unmatched_right_weight"
    QSJ_MATERIALIZE_WEIGHT[$i]="$sj_materialize_weight"; QSJ_FILTER_BUILD_WEIGHT[$i]="$sj_filter_build_weight"
    QSJ_REPLAY_WEIGHT[$i]="$sj_replay_weight"; QSJ_LOOKUP_WEIGHT[$i]="$sj_lookup_weight"
    QSJ_EMIT_WEIGHT[$i]="$sj_emit_weight"
    QOFFM[$i]="$offm"; QONM[$i]="$onm"; QRATIOM[$i]="$ratiom"
    QEFFECTIVE_PASS[$i]="$PASS"; QDUCKDB_PLAN[$i]="$duckdb_plan"; QENABLED_PLAN[$i]="$enabled_plan"
    QTRACE_FILE[$i]="$trace_file"; QCOST_FILE[$i]="$cost_file"
    # ---- append to TXT and CSV ----
    local primary_line detail_line detail_suffix gate_detail
    printf -v primary_line \
        '[%3d/%d] %-36s correct=%s reorder=%s selected=%s kernel=%s threads=%s  TM:off=%s on=%s spd=%s' \
        "$((i+1))" "${#LABELS[@]}" "$id" "$correct" "$outer_reordered" "$selected_plan" \
        "$kernel_display" "$OY_THREADS" "$offm" "$onm" "$ratiom"
    printf -v detail_line \
        '  details: family=%s sql=%s pass=%s timeout=%ss note=%s rows=%s nrel=%s' \
        "$family" "$sql_path" "$PASS" "$OY_TIMEOUT_SECS" "$note" "$rows" "$nrel"
    if [ "$PROFILE" = 1 ]; then
        printf -v detail_suffix \
            ' profile=[status=%s threads=%s Total-Time=%ss CPU-Time=%ss R1=%ss R2=%ss R3=%ss OtherCPU=%ss samples=%s directory=%s]' \
            "$profile_status" "$profile_threads" "$profile_wall" "$profile_cpu" "$r1sj" "$r2sj" \
            "$realjoin" "$other" "$profile_samples" "$profile_directory"
        detail_line+="$detail_suffix"
    fi
    if [ "$correct" = "TRUE" ]; then
        printf -v detail_suffix \
            ' decision=[mode=%s reason=%s raw_winner=%s gate=%s gate_applied=%s proven_empty=%s outer_yan_selected=%s formula=%s]' \
            "$selection_mode" \
            "$decision" "$raw_winner" "$gate_result" "$gate_applied" "$proven_empty" \
            "$selected" "$formula_id"
        detail_line+="$detail_suffix"
        printf -v detail_suffix \
            ' risk=[default_filter_upper_checked=%s selected=%s retained=%s amplification=%s guard=%s full_reduction_bound=%s stretch_eligible=%s stretch_selected=%s join_input_ratio=%s]' \
            "$default_filter_upper_checked" "$default_filter_upper_selected" \
            "$semijoin_retained_ratio" "$uncertain_filter_amplification" "$uncertain_filter_guard" \
            "$full_reduction_lower_bound" "$stretch_eligible" "$stretch_selected" "$join_input_ratio"
        detail_line+="$detail_suffix"
        if [ "$ker" = "hash" ] || [ "$ker" = "mixed" ]; then
            printf -v detail_suffix ' kernel_notice=[HASH-FALLBACK reasons=%s default_bitmap_budget_bytes=34359738368]' \
                "$kreasons"
            detail_line+="$detail_suffix"
            printf 'NOTICE %s: %s; hash reasons=%s. More bitmap memory helps overflow/force_hash after replanning, not ineligible keys.\n' \
                "$id" "$kernel_display" "$kreasons" >&2
        fi
        if [ "$candidate_total" = "NA" ] || [ "$candidate_total" = "-" ] || \
           [ "$baseline_cost" = "NA" ] || [ "$baseline_cost" = "-" ]; then
            detail_line+=" cost=[UNAVAILABLE]"
        else
            printf -v detail_suffix \
                ' cost=[OuterYan=%s + %s*%s = %s; DuckDB=%s; delta=%s; raw_ratio=%s] gate_cmp=[numeric:%s <= %s (= %s*%s); final=%s; margin=%s] SJ=[R1(build=%s probe=%s pairs=%s filters=%s) R2(build=%s probe=%s pairs=%s filters=%s) weighted=%s] weights=[join(inner=%s unmatched_left=%s unmatched_right=%s) SJ(materialize=%s filter_build=%s replay=%s lookup=%s emit=%s)]' \
                "$candidate_join_cost" "$semijoin_cost_ratio" "$semijoin_raw_cost" "$candidate_total" \
                "$baseline_cost" "$raw_delta" "$raw_ratio" \
                "$gate_lhs" "$gate_rhs" "$cost_ratio_limit" "$baseline_cost" "$gate_result" "$gate_margin" \
                "$round1_build" "$round1_probe" "$round1_pairs" "$round1_filters" \
                "$round2_build" "$round2_probe" "$round2_pairs" "$round2_filters" "$weighted_semijoin_cost" \
                "$inner_weight" "$unmatched_left_weight" "$unmatched_right_weight" \
                "$sj_materialize_weight" "$sj_filter_build_weight" "$sj_replay_weight" \
                "$sj_lookup_weight" "$sj_emit_weight"
            detail_line+="$detail_suffix"
        fi
        if [ "$CAPTURE_PLANS" = 1 ]; then
            printf -v detail_suffix ' artifacts=[duckdb=%s enabled=%s trace=%s cost=%s]' \
                "$duckdb_plan" "$enabled_plan" "$trace_file" "$cost_file"
            detail_line+="$detail_suffix"
        fi
    else
        gate_detail="$(printf '%s' "${gate:-ERROR: correctness gate produced no diagnostic}" | tr '\n' ' ')"
        printf -v detail_suffix ' gate_detail=[%s]' "$gate_detail"
        detail_line+="$detail_suffix"
    fi
    {
        echo
        echo "$OY_QUERY_SEPARATOR"
        printf '%s\n%s\n' "$primary_line" "$detail_line"
    } >> "$OUT"
    {
        echo
        echo "$OY_QUERY_SEPARATOR"
        printf '%s\n%s\n' "$primary_line" "$detail_line"
    } >&2
    csv_result_row \
        "$id" "$family" "$sql_path" "$nrel" "$reg" "$outer_reordered" "$gate_applied" "$selected" "$selected_plan" \
        "$proven_empty" "$decision" "$formula_id" "$selection_mode" "$raw_winner" "$gate_result" \
        "$default_filter_upper_checked" "$default_filter_upper_selected" "$full_reduction_lower_bound" \
        "$uncertain_filter_guard" "$stretch_eligible" "$stretch_selected" \
        "$baseline_join_input_rows" "$candidate_join_input_rows" "$join_input_ratio" \
        "$semijoin_retained_ratio" "$uncertain_filter_amplification" \
        "$baseline_cost" "$candidate_join_cost" "$semijoin_raw_cost" "$semijoin_cost_ratio" \
        "$weighted_semijoin_cost" "$candidate_total" "$cost_ratio_limit" "$baseline_threshold" \
        "$round1_build" "$round1_probe" "$round2_build" "$round2_probe" \
        "$round1_pairs" "$round1_filters" "$round2_pairs" "$round2_filters" \
        "$raw_delta" "$raw_ratio" "$gate_lhs" "$gate_rhs" "$gate_margin" \
        "$inner_weight" "$unmatched_left_weight" "$unmatched_right_weight" \
        "$sj_materialize_weight" "$sj_filter_build_weight" "$sj_replay_weight" "$sj_lookup_weight" "$sj_emit_weight" \
        "$ker" "$kdetail" "$kreasons" "$correct" "$note" "$OY_THREADS" \
        "$offm" "$onm" "$ratiom" "$rows" "$PASS" \
        "$duckdb_plan" "$enabled_plan" "$trace_file" "$cost_file" \
        "$profile_status" "$profile_threads" "$r1sj" "$r2sj" "$realjoin" \
        "$r1_operators" "$r2_operators" "$realjoin_operators" \
        "$profile_wall" "$profile_cpu" "$r1ratio" "$r2ratio" "$sjratio" \
        "$realjoin_ratio" "$other" "$other_ratio" "$profile_samples" "$profile_directory"
}

# ==== Every query, once, under the fixed per-statement timeout =============
echo "Temporary result storage: $OY_RUN_TMPDIR" >&2
echo "Temporary filesystem: $OY_TMP_FREE available on $OY_TMP_MOUNT (base=$OY_TMPDIR)" >&2
echo "--- Per-query: correctness + multi-thread timing (TM=${OY_THREADS}) ---" >&2
for ((i=0; i<${#LABELS[@]}; i++)); do
    process_one "$i"
done

# ==== Final summary computed from the Q* arrays =============================
QN="${#LABELS[@]}"
NCORRECT=0; NTIMED=0; NKBM=0; NKHASH=0; NKMIX=0
NNO=0; NYES=0; SUMNO=0; SUMYES=0
NBASELINE=0; NOUTERYAN=0; SUMBASELINE=0; SUMOUTERYAN=0
NSAME=0; NREJECT=0; NSELECTED=0; NDECISION_UNKNOWN=0; NGATE_APPLIED=0
for ((i=0; i<QN; i++)); do
    [ "${QCORRECT[i]}" = "TRUE" ] || continue
    NCORRECT=$((NCORRECT+1))
    case "${QRATIOM[i]}" in ''|NA|-) ;; *) NTIMED=$((NTIMED+1));; esac
    case "${QKER[i]}" in bitmap) NKBM=$((NKBM+1));; hash) NKHASH=$((NKHASH+1));; mixed) NKMIX=$((NKMIX+1));; esac
    [ "${QGATE[i]}" = "1" ] && NGATE_APPLIED=$((NGATE_APPLIED+1))
    case "${QREORDERED[i]}:${QSELECTED[i]}" in
        0:0) NSAME=$((NSAME+1));;
        1:0) NREJECT=$((NREJECT+1));;
        0:1|1:1) NSELECTED=$((NSELECTED+1));;
        *)   NDECISION_UNKNOWN=$((NDECISION_UNKNOWN+1));;
    esac
    case "${QRATIOM[i]}" in ''|NA|-) continue;; esac
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
{
    echo
    echo "============================== SUMMARY ================================"
    echo "queries=$QN  correct=$NCORRECT  incorrect/skipped=$NSKIP  timed=$NTIMED"
    echo "kernel (correct queries): bitmap=$NKBM  hash=$NKHASH  mixed=$NKMIX"
    echo "threads: multi=${OY_THREADS}"
    echo "OuterYan decisions: same-grouping=$NSAME  changed-rejected=$NREJECT  selected=$NSELECTED  unknown=$NDECISION_UNKNOWN  cost-gate-applied=$NGATE_APPLIED"
    echo "coverage by relation count:"
    while IFS= read -r nrel; do
        [ -n "$nrel" ] || continue
        nrel_queries=0; nrel_correct=0; nrel_timed=0
        for ((i=0; i<QN; i++)); do
            [ "${QNREL[i]}" = "$nrel" ] || continue
            nrel_queries=$((nrel_queries+1))
            [ "${QCORRECT[i]}" = "TRUE" ] || continue
            nrel_correct=$((nrel_correct+1))
            case "${QRATIOM[i]}" in ''|NA|-) ;; *) nrel_timed=$((nrel_timed+1));; esac
        done
        echo "  relations=$nrel  queries=$nrel_queries  correct=$nrel_correct  timed=$nrel_timed"
    done < <(printf '%s\n' "${QNREL[@]}" | sort -n -u)
    echo "speed-up by outer_reordered (reorder CSV compatibility column):"
    echo "  No:  n=$NNO  mean speed-up(TM)=$MNO"
    echo "  Yes: n=$NYES  mean speed-up(TM)=$MYES"
    echo "speed-up by outer_yan_selected:"
    echo "  DuckDB baseline: n=$NBASELINE  mean speed-up(TM)=$MBASELINE"
    echo "  OuterYan:        n=$NOUTERYAN  mean speed-up(TM)=$MOUTERYAN"
} >> "$OUT"

echo "Results written to $OUT"
echo "Final CSV written to $CSV_FINAL"
echo "Attempts CSV written to $CSV_ATTEMPTS (single attempt; no retries)"
if [ "$CAPTURE_PLANS" = 1 ]; then
    echo "Plan artifacts written to $PLAN_DIR"
fi
echo "RESULT_TXT=$OUT"
echo "RESULT_CSV=$CSV_FINAL"
echo "RESULT_ATTEMPTS_CSV=$CSV_ATTEMPTS"
if [ "$CAPTURE_PLANS" = 1 ]; then
    echo "RESULT_PLAN_DIR=$PLAN_DIR"
fi
