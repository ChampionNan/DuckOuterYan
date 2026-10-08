#!/usr/bin/env bash
# ============================================================================
# experiment_onoff.sh  —  OuterYan ON-vs-OFF single-sample performance test.
#
# Per corpus query, IN THIS ORDER:
#   1. PLAN DECISION — oy_decision reads OuterYan's machine-readable trace:
#      whether its candidate grouping differs from DuckDB, whether the cost gate
#      ran, and which candidate was selected.
#      A DuckDB fallback, or an aggregate query without an actual aggregate
#      pushdown, skips performance measurements after the correctness check.
#   2. CORRECTNESS — enabled by default for every query, including fallbacks.
#      Compare one OFF/ON bare-query result pair. A mismatch is never timed.
#      A timeout stops only that side; preserve the other side's measurements.
#   3. KERNEL — oy_kernel: which semi-join filter kernel OuterYan committed to
#      (not-run | bitmap(b=N,h=0) | hash(b=0,h=N) | mixed(b=N,h=M) |
#      none(b=0,h=0)), from the DUCKDB_SJ_KERNEL_TRACE diagnostic.
#   4. EACH SIDE — one warm-up, one optional native profile, then one unprofiled
#      timed execution in the same CLI process. OFF/ON use separate processes.
#      The same ON profile supplies optimizer and R1/R2/R3 phase times.
# The default run uses 32 threads; explicit sweeps use separate result files.
# Profiling defaults to on; no single-thread executions are performed.
#
# USAGE: experiment_onoff.sh [options]
#   -b,--bin PATH     duckdb (default build/release/duckdb, else build/debug)
#   -n,--runs N       positive odd timed iterations per config (default 1)
#   -t,--timeout S    set both per-engine statement limits (default 600 each)
#                     on every query; the external timing-batch watchdog is
#                     (N+1+profile)×S plus startup grace per side.
#      --duckdb-timeout S    independent DuckDB/OFF limit
#      --outeryan-timeout S  independent OuterYan/ON limit
#      --only select|agg|pred|tpch|tpcds|job|graph|bench|all  query families
#                     (default all); bench = tpch+tpcds+job
#      --pattern GLOB  only queries whose label matches (default *)
#      --exclude GLOB  skip labels matching any '|'-separated glob
#      --limit N       cap number of queries (0 = no cap, default 0)
#      --query-list FILE  ordered corpus-relative SQL paths (requires --only all)
#      --query-type all|join|graph|aggregate  select a query type (default all)
#      --all            run the deduplicated corpus once (default)
#      --corpus-scope benchmark|selectivity-stress|job-regressions
#                       diagnostic scopes reference existing unique SQL
#      --capture-plans   save OFF/ON EXPLAIN, trace, and detailed cost artifacts
#      --threads LIST    thread counts, e.g. "16 32" or 16,32 (default 32)
#      --profile         collect ON phase plus OFF/ON optimizer metrics (default)
#      --no-profile      skip phase/optimizer profiles; timing stays unprofiled
#      --check-correctness     compare all bare-query result multisets (default)
#      --no-check-correctness  explicitly opt out of result comparison
#   -o,--out FILE     results base (default experiment_onoff_<timestamp>_t<N>.txt)
# ============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CALLER_OY_CORPUS_SET="${OY_CORPUS+x}"
# Unified config: defines DUCKDB_BIN, GRAPH_DATASET, TPCH_SF/TPCDS_SF,
# OY_TIMEOUT_SECS, OY_RUNS.
. "$SCRIPT_DIR/configs.sh"
. "$SCRIPT_DIR/thread_sweep.sh"
. "$SCRIPT_DIR/phase_profile.sh"
[ -x "$DUCKDB_BIN" ] || export DUCKDB_BIN="$REPO_ROOT/build/debug/duckdb"
CORPUS="${OY_CORPUS:-}"
CORPUS_REVISION="custom"
CORPUS_SCOPE="${OY_CORPUS_SCOPE:-benchmark}"
QUERY_TYPE="all"
[ -z "${OY_CORPUS_VERSION:-}" ] || {
    echo "OY_CORPUS_VERSION is retired; unset it and select --query-type instead" >&2; exit 2;
}

RUNS="${OY_RUNS:-1}"; ONLY="all"; PATTERN="*"; EXCLUDE=""; LIMIT=0; OUT=""
QUERY_LIST=""; CAPTURE_PLANS="${OY_CAPTURE_PLANS:-0}"
PROFILE="${OY_PROFILE:-1}"
CHECK_CORRECTNESS="${OY_CHECK_CORRECTNESS:-1}"
THREAD_COUNTS="${OY_THREAD_COUNTS:-$OY_THREADS}"
DUCKDB_TIMEOUT_CLI=""; OUTERYAN_TIMEOUT_CLI=""
ORIGINAL_ARGS=("$@")
while [ $# -gt 0 ]; do case "$1" in
    -b|--bin) export DUCKDB_BIN="$2"; shift 2;;
    -n|--runs) RUNS="$2"; shift 2;;
    -t|--timeout)
        export OY_TIMEOUT_SECS="$2" OY_DUCKDB_TIMEOUT_SECS="$2" OY_OUTERYAN_TIMEOUT_SECS="$2"; shift 2;;
    --duckdb-timeout) DUCKDB_TIMEOUT_CLI="$2"; shift 2;;
    --outeryan-timeout) OUTERYAN_TIMEOUT_CLI="$2"; shift 2;;
    --only) ONLY="$2"; shift 2;;
    --pattern) PATTERN="$2"; shift 2;;
    --exclude) EXCLUDE="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    --query-list) QUERY_LIST="$2"; shift 2;;
    --version|--corpus-version) echo "Version selection is retired; use --query-type join, graph, or aggregate" >&2; exit 2;;
    --query-type) QUERY_TYPE="$2"; shift 2;;
    --corpus-scope) CORPUS_SCOPE="$2"; shift 2;;
    --all) QUERY_TYPE="all"; shift;;
    --capture-plans) CAPTURE_PLANS=1; shift;;
    --profile) PROFILE=1; shift;;
    --no-profile) PROFILE=0; shift;;
    --check-correctness) CHECK_CORRECTNESS=1; shift;;
    --no-check-correctness) CHECK_CORRECTNESS=0; shift;;
    --threads)
        [ $# -ge 2 ] || { echo "--threads requires a value" >&2; exit 2; }
        THREAD_COUNTS="$2"; shift 2;;
    -o|--out) OUT="$2"; shift 2;;
    -h|--help) sed -n '2,/^set /p' "${BASH_SOURCE[0]}"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 2;; esac; done
case "$QUERY_TYPE" in
    all|join|graph|aggregate) ;;
    *) echo "--query-type must be all, join, graph, or aggregate" >&2; exit 2;;
esac
case "$CORPUS_SCOPE" in
    benchmark) ;;
    selectivity-stress|job-regressions)
        [ -z "$QUERY_LIST" ] || { echo "--corpus-scope cannot be combined with --query-list" >&2; exit 2; }
        QUERY_LIST="$CORPUS/${CORPUS_SCOPE//-/_}.txt";;
    *) echo "--corpus-scope must be benchmark, selectivity-stress, or job-regressions" >&2; exit 2;;
esac
[ -z "$QUERY_LIST" ] || [ "$ONLY" = "all" ] || {
    echo "Query-list and diagnostic scopes require --only all" >&2; exit 2;
}
WORKLOAD_CATEGORY="$QUERY_TYPE"
QUERY_CLASS="$QUERY_TYPE"
[ -d "$CORPUS" ] || {
    echo "Corpus directory not found: $CORPUS (generate with: python3 auto_test/gen_outerjoin_benchmark.py)" >&2
    exit 2
}
if [ -f "$CORPUS/manifest.csv" ]; then
    CORPUS_REVISION="$(python3 - "$CORPUS/manifest.csv" <<'PY'
import csv, sys
with open(sys.argv[1], newline='') as handle:
    revisions = {r.get('corpus_revision') or 'custom' for r in csv.DictReader(handle)}
if len(revisions) != 1:
    sys.exit('Corpus manifest must have one revision')
print(revisions.pop())
PY
    )" || exit 2
fi
case "$RUNS" in
    ''|*[!0-9]*|0) echo "--runs must be a positive integer (got: $RUNS)" >&2; exit 2;;
esac
[ $((RUNS % 2)) -eq 1 ] || { echo "--runs must be odd so one real median execution is selected" >&2; exit 2; }
case "$PROFILE" in 0|1) ;; *) echo "OY_PROFILE must be 0 or 1" >&2; exit 2;; esac
case "$CHECK_CORRECTNESS" in 0|1) ;; *) echo "OY_CHECK_CORRECTNESS must be 0 or 1" >&2; exit 2;; esac
CORRECTNESS_MODE="disabled"
[ "$CHECK_CORRECTNESS" = 0 ] || CORRECTNESS_MODE="enabled"
TIMING_PROTOCOL="warm-profile-then-timing-v1"
TIMING_ESTIMATOR="single_post_warmup"
[ "$RUNS" = 1 ] || TIMING_ESTIMATOR="median_post_warmup"
oy_parse_thread_counts "$THREAD_COUNTS" || exit $?
# One experiment start timestamp, captured the moment this script begins (before
# the DB-build phase). Used for BOTH the .txt/.csv filenames AND the in-file
# header, so the txt, its corresponding csv, and the printed time all agree and
# all read as "when experiment_onoff.sh started". Single `date` call so the
# filename form and human form can never straddle a second boundary.
_now="$(date '+%Y%m%d_%H%M%S|%F %T')"
START_TS="${_now%%|*}"; START_HUMAN="${_now##*|}"
EXPERIMENT_GROUP="${OY_EXPERIMENT_GROUP:-$START_TS}"
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
_scope_suffix=""
[ "$CORPUS_SCOPE" = "benchmark" ] || _scope_suffix="_${CORPUS_SCOPE}"
_default_out="$SCRIPT_DIR/results/experiment_onoff${_scope_suffix}_${START_TS}_t${OY_THREADS}.txt"
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
: "${OY_TIMEOUT_SECS:=600}"
[ -z "$DUCKDB_TIMEOUT_CLI" ] || OY_DUCKDB_TIMEOUT_SECS="$DUCKDB_TIMEOUT_CLI"
[ -z "$OUTERYAN_TIMEOUT_CLI" ] || OY_OUTERYAN_TIMEOUT_SECS="$OUTERYAN_TIMEOUT_CLI"
: "${OY_BATCH_GRACE_SECS:=30}"
case "$OY_TIMEOUT_SECS" in
    ''|*[!0-9]*) echo "--timeout must be a non-negative integer (got: $OY_TIMEOUT_SECS)" >&2; exit 2;;
esac
for side_limit in "$OY_DUCKDB_TIMEOUT_SECS" "$OY_OUTERYAN_TIMEOUT_SECS"; do
    case "$side_limit" in
        ''|*[!0-9]*) echo "Engine timeout must be a non-negative integer (got: $side_limit)" >&2; exit 2;;
    esac
done
RECORDED_TIMEOUT="NA"
[ "$OY_DUCKDB_TIMEOUT_SECS" != "$OY_OUTERYAN_TIMEOUT_SECS" ] || RECORDED_TIMEOUT="$OY_DUCKDB_TIMEOUT_SECS"
case "$OY_BATCH_GRACE_SECS" in
    ''|*[!0-9]*) echo "OY_BATCH_GRACE_SECS must be a non-negative integer" >&2; exit 2;;
esac
OY_TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
OY_QUERY_SEPARATOR="===================================================================================================="

# DuckDB enforces this limit independently for every statement. The external
# `timeout` remains a process watchdog and is scaled only to contain all fixed-
# limit statements in a multi-statement timing/profile batch. A timed-out
# statement fails that query's phase immediately: the harness never retries it
# and never raises its per-statement limit.
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
    if [ -n "$OY_TIMEOUT_BIN" ] && [ "$OY_TIMEOUT_SECS" != 0 ]; then
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
# Enabled by default. A mismatch/error blocks paired timing. A timeout stops
# only that engine: the other engine may still be measured, without claiming
# equivalence or an exact speed-up. Each process has its own fixed timeout.
# RETURNS: 0 PASS | 1 FAIL (rows differ) | 2 ERROR | 3 TIMEOUT.
oy_equiv_check() {
    local db="$1" label="$2" query="$3"
    local off on eoff eon esort sql side setting output errors status duck_rc
    local off_rows=0 on_rows=0 rc=0 OY_TIMEOUT_SECS
    off=$(mktemp); on=$(mktemp); eoff=$(mktemp); eon=$(mktemp); esort=$(mktemp); sql=$(mktemp)
    # Called directly, not in a command substitution: these outcomes gate each
    # engine independently after both bare-query attempts have completed.
    OY_EQ_DUCKDB_STATUS=not-run
    OY_EQ_OUTERYAN_STATUS=not-run
    for side in off on; do
        if [ "$side" = off ]; then
            OY_TIMEOUT_SECS="$OY_DUCKDB_TIMEOUT_SECS"
            setting="$OY_OFF"; output="$off"; errors="$eoff"
        else
            OY_TIMEOUT_SECS="$OY_OUTERYAN_TIMEOUT_SECS"
            setting="$OY_ON"; output="$on"; errors="$eon"
        fi
        printf '%s\n%s\n%s;\n' \
            "CALL disable_profiling();PRAGMA threads=${OY_THREADS};$(oy_statement_timeout_sql "$OY_TIMEOUT_SECS")" \
            "$setting" "${query%;}" > "$sql"
        duck_rc=0
        oy_duck "$db" -csv -noheader < "$sql" > "$output" 2>"$errors" || duck_rc=$?
        status=ok
        if [ "$duck_rc" -eq 124 ] || grep -qiE 'Error:.*(maximum execution time|timeout|interrupt)' "$errors"; then
            echo "  TIMEOUT (${OY_TIMEOUT_SECS}s, $side): $label"
            status=timeout
        elif [ "$duck_rc" -ne 0 ] || grep -q 'Error:' "$errors"; then
            echo "  ERROR ($side rc=$duck_rc): $label"
            { grep -m1 'Error:' "$errors" || sed -n '1p' "$errors"; } | sed 's/^/        /'
            status=error
        else
            if [ "$side" = off ]; then off_rows="$(wc -l < "$output" | tr -d ' ')"
            else on_rows="$(wc -l < "$output" | tr -d ' ')"; fi
            if ! LC_ALL=C sort -o "$output" "$output" 2>"$esort"; then
                echo "  ERROR (sort $side): $label"
                sed -n '1p' "$esort" | sed 's/^/        /'
                status=error
            fi
        fi
        if [ "$side" = off ]; then OY_EQ_DUCKDB_STATUS="$status"
        else OY_EQ_OUTERYAN_STATUS="$status"; fi
    done
    if [ "$OY_EQ_DUCKDB_STATUS" = timeout ] || [ "$OY_EQ_OUTERYAN_STATUS" = timeout ]; then
        rc=3
    elif [ "$OY_EQ_DUCKDB_STATUS" != ok ] || [ "$OY_EQ_OUTERYAN_STATUS" != ok ]; then
        rc=2
    elif diff -q "$off" "$on" >/dev/null; then
        echo "  equiv OK: $label ($off_rows rows)"
    else
        echo "  NOT EQUIV: $label (off=$off_rows on=$on_rows)"
        diff "$off" "$on" | head -6 | sed 's/^/        /'
        rc=1
    fi
    rm -f "$off" "$on" "$eoff" "$eon" "$esort" "$sql"
    return "$rc"
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
#                 unary_filter_selectivity=N|NA \
#                 low_selectivity_cost_gate_eligible=0|1 \
#                 low_selectivity_cost_gate_selected=0|1 \
#                 low_selectivity_cost_ratio_limit=N|NA \
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
OY_DECISION_AGGREGATE_QUERY="NA"
OY_DECISION_AGGREGATE_PUSHDOWN_APPLIED="NA"
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
OY_DECISION_UNARY_FILTER_SELECTIVITY="NA"
OY_DECISION_LOW_SELECTIVITY_ELIGIBLE="NA"
OY_DECISION_LOW_SELECTIVITY_SELECTED="NA"
OY_DECISION_LOW_SELECTIVITY_LIMIT="NA"
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
OY_DECISION_EXECUTED_ROUND1_PAIRS="NA"
OY_DECISION_EXECUTED_ROUND1_FILTERS="NA"
OY_DECISION_EXECUTED_ROUND2_PAIRS="NA"
OY_DECISION_EXECUTED_ROUND2_FILTERS="NA"
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
    OY_DECISION_AGGREGATE_QUERY="NA"
    OY_DECISION_AGGREGATE_PUSHDOWN_APPLIED="NA"
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
    OY_DECISION_UNARY_FILTER_SELECTIVITY="NA"
    OY_DECISION_LOW_SELECTIVITY_ELIGIBLE="NA"
    OY_DECISION_LOW_SELECTIVITY_SELECTED="NA"
    OY_DECISION_LOW_SELECTIVITY_LIMIT="NA"
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
    OY_DECISION_EXECUTED_ROUND1_PAIRS="NA"
    OY_DECISION_EXECUTED_ROUND1_FILTERS="NA"
    OY_DECISION_EXECUTED_ROUND2_PAIRS="NA"
    OY_DECISION_EXECUTED_ROUND2_FILTERS="NA"
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
    local OY_TIMEOUT_SECS="$OY_OUTERYAN_TIMEOUT_SECS"
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
        OY_DECISION_AGGREGATE_QUERY="$(oy_record_value "$record" aggregate_query)"
        OY_DECISION_AGGREGATE_PUSHDOWN_APPLIED="$(oy_record_value "$record" aggregate_pushdown_applied)"
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
        OY_DECISION_UNARY_FILTER_SELECTIVITY="$(oy_record_value "$record" unary_filter_selectivity)"
        OY_DECISION_LOW_SELECTIVITY_ELIGIBLE="$(oy_record_value "$record" low_selectivity_cost_gate_eligible)"
        OY_DECISION_LOW_SELECTIVITY_SELECTED="$(oy_record_value "$record" low_selectivity_cost_gate_selected)"
        OY_DECISION_LOW_SELECTIVITY_LIMIT="$(oy_record_value "$record" low_selectivity_cost_ratio_limit)"
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
        OY_DECISION_EXECUTED_ROUND1_PAIRS="$(oy_record_value "$record" executed_round1_pairs)"
        OY_DECISION_EXECUTED_ROUND1_FILTERS="$(oy_record_value "$record" executed_round1_filters)"
        OY_DECISION_EXECUTED_ROUND2_PAIRS="$(oy_record_value "$record" executed_round2_pairs)"
        OY_DECISION_EXECUTED_ROUND2_FILTERS="$(oy_record_value "$record" executed_round2_filters)"
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
        case "$OY_DECISION_DEFAULT_FILTER_UPPER_CHECKED:$OY_DECISION_DEFAULT_FILTER_UPPER_SELECTED:$OY_DECISION_FULL_REDUCTION_LOWER_BOUND:$OY_DECISION_UNCERTAIN_FILTER_GUARD:$OY_DECISION_STRETCH_ELIGIBLE:$OY_DECISION_STRETCH_SELECTED:$OY_DECISION_LOW_SELECTIVITY_ELIGIBLE:$OY_DECISION_LOW_SELECTIVITY_SELECTED" in
            [01]:[01]:[01]:[01]:[01]:[01]:[01]:[01]) ;;
            *) OY_DECISION_REASON="TRACE_INVALID";;
        esac
        case "$OY_DECISION_AGGREGATE_QUERY" in
            0|1) ;;
            *) OY_DECISION_REASON="TRACE_INVALID";;
        esac
        case "$OY_DECISION_AGGREGATE_PUSHDOWN_APPLIED" in
            0|1) ;;
            *) OY_DECISION_REASON="TRACE_INVALID";;
        esac
        if [ "$OY_DECISION_AGGREGATE_PUSHDOWN_APPLIED" = 1 ]; then
            case "$OY_DECISION_AGGREGATE_QUERY:$OY_DECISION_SELECTED_PLAN:$OY_DECISION_SELECTED" in
                1:OUTERYAN:1) ;;
                *) OY_DECISION_REASON="TRACE_INVALID";;
            esac
        fi
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
        if [ "$OY_DECISION_LOW_SELECTIVITY_SELECTED" = 1 ]; then
            case "$OY_DECISION_LOW_SELECTIVITY_ELIGIBLE:$OY_DECISION_SELECTED_PLAN:$OY_DECISION_SELECTED:$OY_DECISION_GATE_RESULT:$OY_DECISION_REASON" in
                1:OUTERYAN:1:PASS:COST_OUTERYAN_LOW_SELECTIVITY) ;;
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
    local OY_TIMEOUT_SECS="$OY_OUTERYAN_TIMEOUT_SECS"
    [ "$setting" != "$OY_OFF" ] || OY_TIMEOUT_SECS="$OY_DUCKDB_TIMEOUT_SECS"
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
    local OY_TIMEOUT_SECS="$OY_OUTERYAN_TIMEOUT_SECS"
    local db="$1" query="$2" sqlf errf nbm nhash label rc
    local nforce nbudget nineligible noverflow reasons="" separator=""
    sqlf=$(mktemp); errf=$(mktemp)
    printf '.mode trash\n%s\n%s\n%s\n' "CALL disable_profiling();PRAGMA threads=${OY_THREADS};$(oy_statement_timeout_sql "$OY_TIMEOUT_SECS")" \
        "$OY_ON" "${query%;};" > "$sqlf"
    # Scope the trace to this single run: export before, unset after, so the
    # timing/equivalence oy_duck calls never see the extra stderr.
    export DUCKDB_SJ_KERNEL_TRACE=1
    oy_duck "$db" -noheader < "$sqlf" >/dev/null 2>"$errf"
    rc=$?
    unset DUCKDB_SJ_KERNEL_TRACE
    if grep -qiE 'Error:.*(maximum execution time|timeout|interrupt)' "$errf"; then
        rc=124
    fi
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
    if [ "$rc" -eq 124 ]; then
        echo "not-run|b0h0|$reasons|timeout"
        return
    fi
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
if [ -n "$QUERY_LIST" ]; then
    [ -f "$QUERY_LIST" ] || { echo "Query list not found: $QUERY_LIST" >&2; exit 2; }
    FAMS="$(awk -F/ '!/^[[:space:]]*(#|$)/ {print $1}' "$QUERY_LIST" | LC_ALL=C sort -u | tr '\n' ' ')"
fi
need_graph=0; need_tpch=0; need_tpcds=0; need_job=0
for fam in $FAMS; do
    if [ "$QUERY_TYPE" != all ] && ! compgen -G "$CORPUS/$fam/${QUERY_TYPE}__*.sql" >/dev/null; then
        continue
    fi
    case "$fam" in
    graph) need_graph=1;; tpch) need_tpch=1;; tpcds) need_tpcds=1;;
    job) need_job=1;; esac; done

GRAPH_DB="${GRAPH_DB:-}"; TPCH_DB="${TPCH_DB:-$REPO_ROOT/tpch_${TPCH_SF}.duckdb}"
TPCDS_DB="${TPCDS_DB:-$REPO_ROOT/tpcds_${TPCDS_SF}.duckdb}"
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
LABELS=(); SQLS=(); DBS=(); QUERY_FAMILIES=(); SQL_PATHS=(); RELATION_COUNTS=(); QUERY_TYPES=()

# Count base relations, not SELECT wrappers used for graph input predicates.
# Counting every FROM/JOIN token would mislabel a four-table query as seven.
oy_relation_count() {
    printf '%s\n' "$1" | PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" "${PYTHON_BIN:-python3}" -c \
        'import sys; from benchmark_corpus import count_base_relations; print(count_base_relations(sys.stdin.read()) or "-")'
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
    local full="$CORPUS/$rel" query_type
    query_type="$(basename "$full" .sql)"
    query_type="${query_type%%__*}"
    case "$query_type" in join|graph|aggregate) ;; *) query_type="custom";; esac
    [ "$QUERY_TYPE" = all ] || [ "$QUERY_TYPE" = "$query_type" ] || return 0
    [ -f "$full" ] || { echo "Missing query: $rel" >&2; exit 2; }
    for existing in "${SQL_PATHS[@]:-}"; do
        [ "$existing" != "$rel" ] || { echo "Duplicate query in selection: $rel" >&2; exit 2; }
    done
    fdb="$(db_for_family "$family")" || { echo "Unknown query family: $family" >&2; exit 2; }
    [ -n "$fdb" ] && [ -f "$fdb" ] || { echo "Database unavailable for $rel: $fdb" >&2; exit 2; }
    query_sql="$(<"$full")"
    relation_count="$(oy_relation_count "$query_sql")"
    [ "$relation_count" != "-" ] || { echo "Could not count relations in $rel" >&2; exit 2; }
    QUERY_TYPES+=("$query_type")
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
}

CSV_HEADER=(
    experiment_group corpus_revision corpus_scope workload_category query_class
    query family sql_path relation_count aggregate_query aggregate_pushdown_applied reorder outer_reordered cost_gate_applied outer_yan_selected selected_plan
    baseline_proven_empty decision_reason formula_id selection_mode raw_cost_winner gate_result
    default_filter_upper_bound_checked default_filter_upper_bound_selected
    full_reduction_cardinality_lower_bound_applied uncertain_filter_amplification_guard
    stretch_cost_gate_eligible stretch_cost_gate_selected
    unary_filter_selectivity low_selectivity_cost_gate_eligible low_selectivity_cost_gate_selected
    low_selectivity_cost_ratio_limit
    baseline_join_input_rows candidate_join_input_rows candidate_to_baseline_join_input_ratio
    semijoin_retained_cardinality_ratio
    uncertain_filter_cardinality_amplification
    baseline_cost candidate_join_cost semijoin_raw_cost semijoin_cost_ratio weighted_semijoin_cost
    candidate_total cost_ratio_limit baseline_threshold round1_build round1_probe round2_build round2_probe
    round1_pairs round1_filters round2_pairs round2_filters
    raw_cost_delta raw_cost_ratio gate_lhs gate_rhs gate_margin
    inner_output_weight unmatched_left_weight unmatched_right_weight semijoin_materialize_weight
    semijoin_filter_build_weight semijoin_replay_weight semijoin_probe_lookup_weight semijoin_probe_emit_weight
    kernel kernel_detail kernel_hash_reasons correct note timing_status timing_threads tm_off tm_on tm_speedup
    optimizer_profile_status optimizer_timed_samples
    optimizer_duckdb_total_s optimizer_outeryan_total_s optimizer_overhead_s optimizer_outeryan_to_duckdb_ratio
    optimizer_duckdb_measured_phase_s optimizer_outeryan_measured_phase_s
    optimizer_duckdb_other_s optimizer_outeryan_other_s
    optimizer_duckdb_phases_json optimizer_outeryan_phases_json optimizer_phase_delta_json optimizer_profile_directory
    rows effective_pass duckdb_plan enabled_plan trace_file cost_file
    profile_status profile_threads profile_round1_operator_s profile_round2_operator_s profile_round3_operator_s
    profile_round1_operator_count profile_round2_operator_count profile_round3_operator_count
    profile_wall_time_s profile_total_time_s profile_cpu_time_s
    profile_round1_ratio profile_round2_ratio profile_total_sj_ratio
    profile_round3_ratio profile_other_elapsed_s profile_other_ratio profile_timed_samples profile_directory
    timeout_seconds sql_content_sha256 execution_host database_signature corpus_manifest_sha256
    correctness_check timing_protocol timing_samples timing_estimator warmup_runs_per_side
    duckdb_timeout_seconds outeryan_timeout_seconds duckdb_status outeryan_status
    duckdb_timeout_stage outeryan_timeout_stage duckdb_correctness_status outeryan_correctness_status
    executed_round1_pairs executed_round1_filters executed_round2_pairs executed_round2_filters
)
EXECUTION_HOST="$(hostname)"
CORPUS_MANIFEST_SHA256="-"
if [ -f "$CORPUS/manifest.csv" ]; then
    CORPUS_MANIFEST_SHA256="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$CORPUS/manifest.csv")"
    cp "$CORPUS/manifest.csv" "${OUT%.txt}.manifest.csv"
fi
: > "$CSV_FINAL"
csv_row "$CSV_FINAL" "${CSV_HEADER[@]}"

# Header (truncate + write)
{
    echo "# OuterYan on/off experiment   started $START_HUMAN"
    echo "# binary : $DUCKDB_BIN"
    echo "# corpus : revision=$CORPUS_REVISION, scope=$CORPUS_SCOPE, $ONLY  (pattern=$PATTERN limit=$LIMIT) — ${#LABELS[@]} queries from $CORPUS"
    echo "# class  : workload_category=$WORKLOAD_CATEGORY query_class=$QUERY_CLASS"
    echo "# relations: counted from FROM/JOIN tokens in each flat bare query"
    echo "# tables : $SIZES"
    echo "# timing : threads=${OY_THREADS}, estimator=$TIMING_ESTIMATOR samples=$RUNS; each side: 1 warm-up + $PROFILE profile + $RUNS unprofiled timed; same process"
    echo "# overhead: correctness, diagnostics and TM timing disable profiling; phase/optimizer profiling enabled=$PROFILE"
    echo "# optimize: OFF/ON query execution profiles; 1 unprofiled warm-up + 1 measured sample per side"
    echo "# phases : workflow optimizer phases and execution R1/R2/R3 share the same measured ON execution"
    echo "#          Round 1/2/3 + OtherCPU = aggregate CPU-Time, not wall-clock Total-Time"
    echo "#          successful raw profiles are deleted; failure artifacts, if any: $PROFILE_DIR"
    echo "# timeout: DuckDB=${OY_DUCKDB_TIMEOUT_SECS}s OuterYan=${OY_OUTERYAN_TIMEOUT_SECS}s per statement; independent engines, no retry after a side times out"
    echo "# temp    : base=$OY_TMPDIR run=$OY_RUN_TMPDIR ($OY_TMP_FREE available on $OY_TMP_MOUNT)"
    echo "# correct: check=$CORRECTNESS_MODE; NOT-CHECKED means result equivalence was not verified"
    echo "# fallback: correctness is still checked when enabled; verified fallbacks skip profiling/timing, use timing_status=fallback-skip and policy-default speed-up=1.0"
    echo "# formula : candidate_total = candidate_join_cost + semijoin_cost_ratio * semijoin_raw_cost"
    echo "# gate    : candidate_total <= cost_ratio_limit * baseline_cost"
    echo "# compare : raw_cost_winner compares candidate_total directly with baseline_cost"
    echo "# capture : plans=$CAPTURE_PLANS directory=$PLAN_DIR"
    echo
    echo "===================== PER-QUERY RESULT BLOCKS ========================="
    echo "# Columns: TM = unprofiled wall-clock timing at threads=${OY_THREADS}"
    echo "# Each query has exactly four lines after a full-width separator:"
    echo "#   line 1 = query index and name"
    echo "#   line 2 = correctness, reorder/selection, kernel, runtime, speed-up, optimizer time"
    echo "#   line 3 = family, relations, pass, note, and phase breakdown"
    echo "#   line 4 = decision, formula/cost details, optimizer workflow phases, and artifacts"
    echo "#   kernel = not-run | bitmap(b=N,h=0) | hash(b=0,h=N) | mixed(b=N,h=M) | none(b=0,h=0)"
} > "$OUT"

# Per-query state arrays (index = query #). Written by process_one and read by
# the final summary.
QLBL=(); QNREL=(); QCORRECT=(); QNOTE=(); QROWS=(); QREG=()
QDB=(); QSQL=(); QFAMILY=(); QPATH=(); QKER=(); QKDETAIL=(); QKREASONS=()
QAGGREGATE=(); QAGG_PUSHDOWN=(); QREORDERED=(); QGATE=(); QSELECTED=(); QDECISION=(); QTIMING_STATUS=()
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

# process_one <i> — run the pipeline for query i (decision -> optional check -> kernel
# -> each side's warm-up/profile/timing) under its independent timeout, store the result in the Q*
# arrays at index i, and append one row to TXT and CSV.
process_one() {
    local i="$1"
    local id="${LABELS[i]}" sql="${SQLS[i]}" db="${DBS[i]}"
    local family="${QUERY_FAMILIES[i]}" sql_path="${SQL_PATHS[i]}"
    local nrel="${RELATION_COUNTS[i]}"
    local identity sql_content_sha256 database_signature
    identity="$(python3 - "$CORPUS/$sql_path" "$db" <<'PY'
import hashlib, json, pathlib, sys
sql, db = map(pathlib.Path, sys.argv[1:])
stat = db.stat()
signature = json.dumps([str(db.resolve()), stat.st_size, stat.st_mtime_ns], separators=(',', ':'))
print(hashlib.sha256(sql.read_bytes()).hexdigest(), hashlib.sha256(signature.encode()).hexdigest())
PY
    )" || return 1
    read -r sql_content_sha256 database_signature <<< "$identity"
    local WORKLOAD_CATEGORY="${QUERY_TYPES[i]}" QUERY_CLASS="${QUERY_TYPES[i]}"
    local gate="" correct="FALSE" note="ERROR" rows="-"
    local reg="-" outer_reordered="-" gate_applied="-" selected="-" decision="-"
    local formula_id="-" selection_mode="-" aggregate_query="-" aggregate_pushdown_applied="-" selected_plan="-" proven_empty="-" raw_winner="-" gate_result="-"
    local default_filter_upper_checked="-" default_filter_upper_selected="-" uncertain_filter_guard="-"
    local full_reduction_lower_bound="-" stretch_eligible="-" stretch_selected="-"
    local unary_filter_selectivity="-" low_selectivity_eligible="-" low_selectivity_selected="-"
    local low_selectivity_limit="-"
    local baseline_join_input_rows="-" candidate_join_input_rows="-" join_input_ratio="-"
    local semijoin_retained_ratio="-" uncertain_filter_amplification="-"
    local baseline_cost="-" candidate_join_cost="-" semijoin_raw_cost="-"
    local semijoin_cost_ratio="-" weighted_semijoin_cost="-" candidate_total="-"
    local cost_ratio_limit="-" baseline_threshold="-"
    local round1_build="-" round1_probe="-" round2_build="-" round2_probe="-"
    local round1_pairs="-" round1_filters="-" round2_pairs="-" round2_filters="-"
    local executed_round1_pairs="NA" executed_round1_filters="NA"
    local executed_round2_pairs="NA" executed_round2_filters="NA"
    local raw_delta="-" raw_ratio="-" gate_lhs="-" gate_rhs="-" gate_margin="-"
    local inner_weight="-" unmatched_left_weight="-" unmatched_right_weight="-"
    local sj_materialize_weight="-" sj_filter_build_weight="-" sj_replay_weight="-"
    local sj_lookup_weight="-" sj_emit_weight="-"
    local ker="not-run" kdetail="b0h0" kreasons="-" kernel_status="not-run" kernel_display="not-run"
    local offm="-" onm="-" ratiom="-" timing_status="not-run"
    local duckdb_plan="-" enabled_plan="-" trace_file="-" cost_file="-"
    local profile_status="disabled" profile_threads="-" profile_directory="-"
    local r1sj="NA" r2sj="NA" realjoin="NA" profile_wall="NA" profile_cpu="NA"
    local r1ratio="NA" r2ratio="NA" sjratio="NA" realjoin_ratio="NA" other="NA" other_ratio="NA"
    local r1_operators="NA" r2_operators="NA" realjoin_operators="NA" profile_samples="NA"
    local optimizer_status="disabled" optimizer_samples="NA" optimizer_profile_directory="-"
    local optimizer_duckdb_total="NA" optimizer_outeryan_total="NA" optimizer_overhead="NA"
    local optimizer_ratio="NA" optimizer_duckdb_phase_sum="NA" optimizer_outeryan_phase_sum="NA"
    local optimizer_duckdb_other="NA" optimizer_outeryan_other="NA"
    local optimizer_duckdb_phases="{}" optimizer_outeryan_phases="{}" optimizer_phase_delta="{}"
    local optimizer_focus="-"
    local decision_issue="" plan_issue=""
    local duckdb_status="not-run" outeryan_status="not-run"
    local duckdb_timeout_stage="-" outeryan_timeout_stage="-"
    local duckdb_correctness_status="disabled" outeryan_correctness_status="disabled"
    if [ "$PROFILE" = 1 ]; then
        profile_status="not-correct"
        optimizer_status="not-correct"
    fi
    if [ "$CAPTURE_PLANS" = 1 ]; then
        local artifact_stem="$PLAN_DIR/${family}__${id}.${PASS}"
        duckdb_plan="${artifact_stem}.duckdb.plan.txt"
        enabled_plan="${artifact_stem}.enabled.plan.txt"
        trace_file="${artifact_stem}.trace.txt"
        cost_file="${artifact_stem}.cost.txt"
    fi

    # Decide first. Only a DuckDB fallback returns the exact baseline logical
    # plan; selected OuterYan aggregate queries are timed with or without
    # pushdown. Keep fallback rows for workload coverage with an explicit
    # policy-default speed-up of 1.0.
    oy_decision "$db" "$sql" \
        "$([ "$CAPTURE_PLANS" = 1 ] && printf '%s' "$trace_file")" \
        "$([ "$CAPTURE_PLANS" = 1 ] && printf '%s' "$cost_file")"
        formula_id="$OY_DECISION_FORMULA_ID"
        selection_mode="$OY_DECISION_SELECTION_MODE"
        aggregate_query="$OY_DECISION_AGGREGATE_QUERY"
        aggregate_pushdown_applied="$OY_DECISION_AGGREGATE_PUSHDOWN_APPLIED"
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
        unary_filter_selectivity="$OY_DECISION_UNARY_FILTER_SELECTIVITY"
        low_selectivity_eligible="$OY_DECISION_LOW_SELECTIVITY_ELIGIBLE"
        low_selectivity_selected="$OY_DECISION_LOW_SELECTIVITY_SELECTED"
        low_selectivity_limit="$OY_DECISION_LOW_SELECTIVITY_LIMIT"
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
        executed_round1_pairs="$OY_DECISION_EXECUTED_ROUND1_PAIRS"
        executed_round1_filters="$OY_DECISION_EXECUTED_ROUND1_FILTERS"
        executed_round2_pairs="$OY_DECISION_EXECUTED_ROUND2_PAIRS"
        executed_round2_filters="$OY_DECISION_EXECUTED_ROUND2_FILTERS"
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
            *) decision_issue="TRACE-INCONSISTENT";;
        esac

    if [ "$CAPTURE_PLANS" = 1 ]; then
        oy_capture_plan "$db" "$OY_OFF" "$sql" "$duckdb_plan" || plan_issue="OFF-PLAN-ERROR"
        oy_capture_plan "$db" "$OY_ON" "$sql" "$enabled_plan" || plan_issue="${plan_issue:+$plan_issue;}ON-PLAN-ERROR"
    fi

    local fallback_skip=0
    case "$decision" in
        TRACE_ERROR|TRACE_MISSING|TRACE_INVALID) ;;
        *)
            # No aggregate pushdown does not imply an unchanged plan: an
            # OuterYan-selected query can still use a different join/SJ tree.
            if [ "$selected_plan:$selected" = "DUCKDB:0" ]; then
                fallback_skip=1
            fi
            ;;
    esac
    if [ "$CHECK_CORRECTNESS" = 0 ]; then
        correct="NOT-CHECKED"
        note="OK;CORRECTNESS-NOT-CHECKED"
        [ "$fallback_skip" = 0 ] || correct="SKIPPED"
    else
        local gate_file
        gate_file="$(mktemp)" || return 1
        oy_equiv_check "$db" "$id" "$sql" > "$gate_file"
        gate="$(< "$gate_file")"
        rm -f "$gate_file"
        duckdb_correctness_status="$OY_EQ_DUCKDB_STATUS"
        outeryan_correctness_status="$OY_EQ_OUTERYAN_STATUS"
        case "$gate" in
            *"equiv OK"*)  correct="TRUE";  note="OK";        rows="$(printf '%s' "$gate" | grep -oE '[0-9]+ rows' | grep -oE '[0-9]+')";;
            *"NOT EQUIV"*) correct="FALSE"; note="NOT-EQUIV"; rows="$(printf '%s' "$gate" | grep -oE 'off=[0-9]+ on=[0-9]+')";;
            *"TIMEOUT"*)   correct="TIMEOUT"; note="TIMEOUT"; rows="-";;
            *)             correct="FALSE"; note="ERROR";     rows="-";;
        esac
    fi
    local off_ready=0 on_ready=0
    case "$correct" in
        TRUE|NOT-CHECKED) off_ready=1; on_ready=1;;
        TIMEOUT)
            # The completed side can still be measured, but a censored pair
            # cannot establish equivalence or an exact speed-up.
            [ "$duckdb_correctness_status" != ok ] || off_ready=1
            [ "$outeryan_correctness_status" != ok ] || on_ready=1;;
        FALSE) duckdb_status=correctness-failed; outeryan_status=correctness-failed;;
    esac
    if [ "$duckdb_correctness_status" = timeout ]; then
        duckdb_status=timeout; duckdb_timeout_stage=correctness
        note="${note};TIMEOUT-OFF-CORRECTNESS"
    fi
    if [ "$outeryan_correctness_status" = timeout ]; then
        outeryan_status=timeout; outeryan_timeout_stage=correctness
        note="${note};TIMEOUT-ON-CORRECTNESS"
    fi
    if [ "$fallback_skip" = 1 ]; then
        [ "$off_ready" = 0 ] || duckdb_status=fallback-skip
        [ "$on_ready" = 0 ] || outeryan_status=fallback-skip
        if [ "$correct" = TRUE ] || [ "$correct" = SKIPPED ]; then
            note="FALLBACK-SKIP"; timing_status=fallback-skip
            duckdb_status=fallback-skip; outeryan_status=fallback-skip
            offm="NA"; onm="NA"; ratiom="1.000"
            profile_status=fallback-skip; optimizer_status=fallback-skip
        fi
        off_ready=0; on_ready=0
    fi
    [ -z "$decision_issue" ] || note="${note};$decision_issue"
    [ -z "$plan_issue" ] || note="${note};$plan_issue"

    if [ "$on_ready" = 1 ] && [ "$selected_plan" = OUTERYAN ]; then
        local kraw
        kraw="$(oy_kernel "$db" "$sql")"
        IFS='|' read -r ker kdetail kreasons kernel_status <<< "$kraw"
        if [ "$kernel_status" = timeout ]; then
            note="${note};TIMEOUT-ON-KERNEL"
            outeryan_status=timeout; outeryan_timeout_stage=kernel
            on_ready=0
        elif [ "$kernel_status" != ok ]; then
            note="${note};KERNEL-TRACE-ERROR"
        fi
    fi
    kernel_display="$(oy_kernel_display "$ker" "$kdetail")"

    if [ "$off_ready" = 1 ] || [ "$on_ready" = 1 ]; then
        local measurement_root="$OY_RUN_TMPDIR"
        [ "$PROFILE" = 0 ] || measurement_root="$PROFILE_DIR"
        optimizer_profile_directory="$(mktemp -d "$measurement_root/${family}__${id}.optimizer.XXXXXX")" || {
            note="${note};MEASUREMENT-DIRECTORY-ERROR"
            [ "$off_ready" = 0 ] || duckdb_status=error
            [ "$on_ready" = 0 ] || outeryan_status=error
            off_ready=0; on_ready=0
            optimizer_profile_directory="-"
        }
    fi
    local side setting limit ready measured measurement_rc stage
    for side in duckdb outeryan; do
        if [ "$side" = duckdb ]; then
            ready="$off_ready"; setting="$OY_OFF"; limit="$OY_DUCKDB_TIMEOUT_SECS"
        else
            ready="$on_ready"; setting="$OY_ON"; limit="$OY_OUTERYAN_TIMEOUT_SECS"
        fi
        [ "$ready" = 1 ] || continue
        measured="$(oy_warm_profile_time "$db" "$setting" "$sql" "$OY_THREADS" "$RUNS" \
                    "$optimizer_profile_directory" "$side" "$PROFILE" "$limit")"
        measurement_rc=$?
        if [ "$measurement_rc" = 0 ]; then
            if [ "$side" = duckdb ]; then
                offm="${measured%% *}"; duckdb_status=measured
            else
                onm="${measured%% *}"; outeryan_status=measured
            fi
        elif [ "$measurement_rc" = 124 ]; then
            stage="$(awk -F: '/^OY_STAGE:/ {stage=$2} END {print stage ? stage : "batch"}' \
                      "$optimizer_profile_directory/optimizer_${side}.log")"
            if [ "$side" = duckdb ]; then
                duckdb_status=timeout; duckdb_timeout_stage="$stage"
                note="${note};TIMEOUT-OFF-$(printf '%s' "$stage" | tr '[:lower:]' '[:upper:]')"
            else
                outeryan_status=timeout; outeryan_timeout_stage="$stage"
                note="${note};TIMEOUT-ON-$(printf '%s' "$stage" | tr '[:lower:]' '[:upper:]')"
            fi
        else
            if [ "$side" = duckdb ]; then duckdb_status=error; note="${note};OFF-TIMING-ERROR"
            else outeryan_status=error; note="${note};ON-TIMING-ERROR"; fi
        fi
    done

    if [ "$duckdb_status" = measured ] && [ "$outeryan_status" = measured ]; then
        timing_status=measured
        ratiom="$(awk -v off="$offm" -v on="$onm" 'BEGIN {printf "%.3f", off/on}')"
    elif [ "$duckdb_status" = timeout ] || [ "$outeryan_status" = timeout ]; then
        timing_status=timeout; ratiom="NA"
    elif [ "$duckdb_status" = error ] || [ "$outeryan_status" = error ]; then
        timing_status=error; ratiom="NA"
    fi
    if [ "$timing_status" != not-run ]; then
        [ "$duckdb_status" = measured ] || offm="NA"
        [ "$outeryan_status" = measured ] || onm="NA"
    fi
    if [ "$PROFILE" = 1 ] && [ "$timing_status" = timeout ]; then
        optimizer_status=not-run
        profile_status=not-run
        [ "$outeryan_status" != timeout ] || profile_status=timeout
    fi

    if [ "$PROFILE" = 1 ] && [ "$optimizer_profile_directory" != "-" ]; then
        local profile_mode="" optimizer_raw optimizer_rc=0
        local -a optimizer_fields=()
        if [ "$duckdb_status" = measured ] && [ "$outeryan_status" = measured ]; then profile_mode=both
        elif [ "$duckdb_status" = measured ]; then profile_mode=duckdb
        elif [ "$outeryan_status" = measured ]; then profile_mode=outeryan; fi
        optimizer_status=not-run
        profile_status=not-run
        [ "$outeryan_status" != timeout ] || profile_status=timeout
        if [ -n "$profile_mode" ]; then
            optimizer_raw="$(oy_optimizer_profile_from_files "$optimizer_profile_directory" "$sql" "$profile_mode")" \
                || optimizer_rc=$?
            IFS='|' read -r -a optimizer_fields <<< "$optimizer_raw"
            if [ "$optimizer_rc" = 0 ] && [ "${#optimizer_fields[@]}" -eq 13 ] && \
               { [ "${optimizer_fields[0]}" != NA ] || [ "${optimizer_fields[1]}" != NA ]; }; then
                IFS='|' read -r optimizer_duckdb_total optimizer_outeryan_total optimizer_overhead \
                    optimizer_ratio optimizer_duckdb_phase_sum optimizer_outeryan_phase_sum \
                    optimizer_duckdb_other optimizer_outeryan_other optimizer_samples \
                    optimizer_duckdb_phases optimizer_outeryan_phases optimizer_phase_delta optimizer_focus \
                    <<< "$optimizer_raw"
                optimizer_status=PARTIAL
                [ "$profile_mode" != both ] || optimizer_status=OK
            else
                optimizer_status=ERROR
                note="${note};OPTIMIZER-PROFILE-ERROR"
                echo "OPTIMIZER-PROFILE-ERROR: $id; see $optimizer_profile_directory" >&2
            fi
        fi
        if [ "$outeryan_status" = measured ]; then
            profile_status=not-selected
            if [ "$selected_plan" = OUTERYAN ]; then
                local praw profile_rc=0
                local -a profile_fields=()
                profile_threads="$OY_THREADS"
                profile_status=ERROR
                if [ "$optimizer_status" = OK ] || [ "$optimizer_status" = PARTIAL ]; then
                    # The final profiled plan can omit reducers after the cost
                    # gate. Never validate its phases against pre-RBO estimates
                    # when actual schedule metadata is available. Prefer the
                    # profiled decision over the separate EXPLAIN observation.
                    local profiled_decision value expected_r1 expected_r2
                    profiled_decision="$(awk '/^\[OY_DECISION\]/ {record=$0} END {print record}' \
                        "$optimizer_profile_directory/optimizer_outeryan.trace")"
                    value="$(oy_record_value "$profiled_decision" executed_round1_pairs)"
                    [ "$value" = NA ] || executed_round1_pairs="$value"
                    value="$(oy_record_value "$profiled_decision" executed_round1_filters)"
                    [ "$value" = NA ] || executed_round1_filters="$value"
                    value="$(oy_record_value "$profiled_decision" executed_round2_pairs)"
                    [ "$value" = NA ] || executed_round2_pairs="$value"
                    value="$(oy_record_value "$profiled_decision" executed_round2_filters)"
                    [ "$value" = NA ] || executed_round2_filters="$value"
                    expected_r1="$executed_round1_pairs"; expected_r2="$executed_round2_pairs"
                    [ "$expected_r1" != NA ] || expected_r1="$round1_pairs"
                    [ "$expected_r2" != NA ] || expected_r2="$round2_pairs"
                    praw="$(oy_phase_profile_from_json \
                        "$optimizer_profile_directory/optimizer_outeryan_1.json" "$sql" "$selected_plan" \
                        "$expected_r1" "$expected_r2" "$proven_empty")" || profile_rc=$?
                    read -r -a profile_fields <<< "$praw"
                    if [ "$profile_rc" = 0 ] && [ "${#profile_fields[@]}" -eq 15 ] && \
                       [ "${profile_fields[3]}" != NA ]; then
                        read -r r1sj r2sj realjoin profile_wall profile_cpu r1ratio r2ratio sjratio \
                            realjoin_ratio other other_ratio r1_operators r2_operators realjoin_operators \
                            profile_samples <<< "$praw"
                        profile_status=OK
                    fi
                fi
                if [ "$profile_status" = ERROR ]; then
                    note="${note};PROFILE-ERROR"
                    echo "PROFILE-ERROR: $id; see $optimizer_profile_directory" >&2
                fi
            fi
        fi
        if [ "$optimizer_status" = OK ] && [ "$profile_status" != ERROR ]; then
            rm -f "$optimizer_profile_directory/optimizer_duckdb_1.json" \
                "$optimizer_profile_directory/optimizer_outeryan_1.json" \
                "$optimizer_profile_directory/optimizer_outeryan.trace" \
                "$optimizer_profile_directory/optimizer_duckdb.trace" \
                "$optimizer_profile_directory/optimizer_outeryan.log" \
                "$optimizer_profile_directory/optimizer_duckdb.log"
            if rmdir "$optimizer_profile_directory" 2>/dev/null; then
                optimizer_profile_directory="-"
            fi
        fi
        profile_directory="$optimizer_profile_directory"
    fi
    # Store final state for the summary.
    QLBL[$i]="$id"; QNREL[$i]="$nrel"; QCORRECT[$i]="$correct"; QNOTE[$i]="$note"; QROWS[$i]="$rows"
    QREG[$i]="$reg"; QDB[$i]="$db"; QSQL[$i]="$sql"; QFAMILY[$i]="$family"; QPATH[$i]="$sql_path"
    QKER[$i]="$ker"; QKDETAIL[$i]="$kdetail"; QKREASONS[$i]="$kreasons"
    QAGGREGATE[$i]="$aggregate_query"; QAGG_PUSHDOWN[$i]="$aggregate_pushdown_applied"; QTIMING_STATUS[$i]="$timing_status"
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
    local query_line result_line context_line decision_line detail_suffix gate_detail
    printf -v query_line '[%3d/%d] query=%s' "$((i+1))" "${#LABELS[@]}" "$id"
    printf -v result_line \
        '  result: correct=%s timing=%s aggregate=%s aggregate_pushdown=%s reorder=%s selected=%s kernel=%s threads=%s runtime_s=[DuckDB=%s OuterYan=%s] speedup=%s optimization_s=[status=%s DuckDB=%s OuterYan=%s overhead=%s ratio=%s samples=%s]' \
        "$correct" "$timing_status" "$aggregate_query" "$aggregate_pushdown_applied" "$outer_reordered" "$selected_plan" "$kernel_display" "$OY_THREADS" \
        "$offm" "$onm" "$ratiom" "$optimizer_status" "$optimizer_duckdb_total" \
        "$optimizer_outeryan_total" "$optimizer_overhead" "$optimizer_ratio" "$optimizer_samples"
    result_line+=" measurement=[check=$CORRECTNESS_MODE protocol=$TIMING_PROTOCOL samples=$RUNS estimator=$TIMING_ESTIMATOR warmups=$((1 + PROFILE))]"
    result_line+=" engine_status=[DuckDB=$duckdb_status OuterYan=$outeryan_status DuckDB_timeout_s=$OY_DUCKDB_TIMEOUT_SECS OuterYan_timeout_s=$OY_OUTERYAN_TIMEOUT_SECS DuckDB_timeout_stage=$duckdb_timeout_stage OuterYan_timeout_stage=$outeryan_timeout_stage DuckDB_check=$duckdb_correctness_status OuterYan_check=$outeryan_correctness_status]"
    printf -v context_line \
        '  context: family=%s category=%s nrel=%s pass=%s note=%s rows=%s sql=%s breakdown_s=[status=%s CPU=%s R1=%s R2=%s R3=%s Other=%s wall=%s samples=%s]' \
        "$family" "$WORKLOAD_CATEGORY" "$nrel" "$PASS" "$note" "$rows" "$sql_path" \
        "$profile_status" "$profile_cpu" "$r1sj" "$r2sj" "$realjoin" "$other" "$profile_wall" "$profile_samples"
    decision_line='  decision:'
    if [ "$correct" = "TRUE" ] || [ "$correct" = "NOT-CHECKED" ] || [ "$correct" = "TIMEOUT" ] || [ "$timing_status" = "fallback-skip" ]; then
        printf -v detail_suffix \
            ' plan=[mode=%s reason=%s raw_winner=%s gate=%s gate_applied=%s proven_empty=%s outer_yan_selected=%s formula=%s]' \
            "$selection_mode" \
            "$decision" "$raw_winner" "$gate_result" "$gate_applied" "$proven_empty" \
            "$selected" "$formula_id"
        decision_line+="$detail_suffix"
        printf -v detail_suffix \
            ' risk=[default_filter_upper_checked=%s selected=%s retained=%s amplification=%s guard=%s full_reduction_bound=%s stretch_eligible=%s stretch_selected=%s unary_selectivity=%s low_selectivity_eligible=%s low_selectivity_selected=%s low_selectivity_limit=%s join_input_ratio=%s]' \
            "$default_filter_upper_checked" "$default_filter_upper_selected" \
            "$semijoin_retained_ratio" "$uncertain_filter_amplification" "$uncertain_filter_guard" \
            "$full_reduction_lower_bound" "$stretch_eligible" "$stretch_selected" \
            "$unary_filter_selectivity" "$low_selectivity_eligible" "$low_selectivity_selected" \
            "$low_selectivity_limit" "$join_input_ratio"
        decision_line+="$detail_suffix"
        if [ "$PROFILE" = 1 ]; then
            printf -v detail_suffix \
                ' optimizer_phases=[%s; DuckDB_measured=%ss OuterYan_measured=%ss]' \
                "$optimizer_focus" "$optimizer_duckdb_phase_sum" "$optimizer_outeryan_phase_sum"
            decision_line+="$detail_suffix"
        fi
        if [ "$ker" = "hash" ] || [ "$ker" = "mixed" ]; then
            printf -v detail_suffix ' kernel_notice=[HASH-FALLBACK reasons=%s default_bitmap_budget_bytes=34359738368]' \
                "$kreasons"
            decision_line+="$detail_suffix"
            printf 'NOTICE %s: %s; hash reasons=%s. More bitmap memory helps overflow/force_hash after replanning, not ineligible keys.\n' \
                "$id" "$kernel_display" "$kreasons" >&2
        fi
        if [ "$candidate_total" = "NA" ] || [ "$candidate_total" = "-" ] || \
           [ "$baseline_cost" = "NA" ] || [ "$baseline_cost" = "-" ]; then
            decision_line+=" cost=[UNAVAILABLE]"
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
            decision_line+="$detail_suffix"
        fi
        printf -v detail_suffix ' executed_SJ=[R1(pairs=%s filters=%s) R2(pairs=%s filters=%s)]' \
            "$executed_round1_pairs" "$executed_round1_filters" \
            "$executed_round2_pairs" "$executed_round2_filters"
        decision_line+="$detail_suffix"
        if [ "$CAPTURE_PLANS" = 1 ]; then
            printf -v detail_suffix ' artifacts=[duckdb=%s enabled=%s trace=%s cost=%s]' \
                "$duckdb_plan" "$enabled_plan" "$trace_file" "$cost_file"
            decision_line+="$detail_suffix"
        fi
    fi
    if [ "$correct" != TRUE ] && [ "$correct" != NOT-CHECKED ] && [ "$timing_status" != fallback-skip ]; then
        gate_detail="$(printf '%s' "${gate:-ERROR: correctness gate produced no diagnostic}" | tr '\n' ' ')"
        printf -v detail_suffix ' gate_detail=[%s]' "$gate_detail"
        decision_line+="$detail_suffix"
    fi
    {
        echo
        echo "$OY_QUERY_SEPARATOR"
        printf '%s\n%s\n%s\n%s\n' "$query_line" "$result_line" "$context_line" "$decision_line"
    } >> "$OUT"
    {
        echo
        echo "$OY_QUERY_SEPARATOR"
        printf '%s\n%s\n%s\n%s\n' "$query_line" "$result_line" "$context_line" "$decision_line"
    } >&2
    csv_result_row \
        "$EXPERIMENT_GROUP" "$CORPUS_REVISION" "$CORPUS_SCOPE" "$WORKLOAD_CATEGORY" "$QUERY_CLASS" \
        "$id" "$family" "$sql_path" "$nrel" "$aggregate_query" "$aggregate_pushdown_applied" "$reg" "$outer_reordered" "$gate_applied" "$selected" "$selected_plan" \
        "$proven_empty" "$decision" "$formula_id" "$selection_mode" "$raw_winner" "$gate_result" \
        "$default_filter_upper_checked" "$default_filter_upper_selected" "$full_reduction_lower_bound" \
        "$uncertain_filter_guard" "$stretch_eligible" "$stretch_selected" \
        "$unary_filter_selectivity" "$low_selectivity_eligible" "$low_selectivity_selected" "$low_selectivity_limit" \
        "$baseline_join_input_rows" "$candidate_join_input_rows" "$join_input_ratio" \
        "$semijoin_retained_ratio" "$uncertain_filter_amplification" \
        "$baseline_cost" "$candidate_join_cost" "$semijoin_raw_cost" "$semijoin_cost_ratio" \
        "$weighted_semijoin_cost" "$candidate_total" "$cost_ratio_limit" "$baseline_threshold" \
        "$round1_build" "$round1_probe" "$round2_build" "$round2_probe" \
        "$round1_pairs" "$round1_filters" "$round2_pairs" "$round2_filters" \
        "$raw_delta" "$raw_ratio" "$gate_lhs" "$gate_rhs" "$gate_margin" \
        "$inner_weight" "$unmatched_left_weight" "$unmatched_right_weight" \
        "$sj_materialize_weight" "$sj_filter_build_weight" "$sj_replay_weight" "$sj_lookup_weight" "$sj_emit_weight" \
        "$ker" "$kdetail" "$kreasons" "$correct" "$note" "$timing_status" "$OY_THREADS" \
        "$offm" "$onm" "$ratiom" \
        "$optimizer_status" "$optimizer_samples" "$optimizer_duckdb_total" "$optimizer_outeryan_total" \
        "$optimizer_overhead" "$optimizer_ratio" "$optimizer_duckdb_phase_sum" "$optimizer_outeryan_phase_sum" \
        "$optimizer_duckdb_other" "$optimizer_outeryan_other" \
        "$optimizer_duckdb_phases" "$optimizer_outeryan_phases" "$optimizer_phase_delta" "$optimizer_profile_directory" \
        "$rows" "$PASS" \
        "$duckdb_plan" "$enabled_plan" "$trace_file" "$cost_file" \
        "$profile_status" "$profile_threads" "$r1sj" "$r2sj" "$realjoin" \
        "$r1_operators" "$r2_operators" "$realjoin_operators" \
        "$profile_wall" "$profile_cpu" "$profile_cpu" "$r1ratio" "$r2ratio" "$sjratio" \
        "$realjoin_ratio" "$other" "$other_ratio" "$profile_samples" "$profile_directory" \
        "$RECORDED_TIMEOUT" "$sql_content_sha256" "$EXECUTION_HOST" "$database_signature" "$CORPUS_MANIFEST_SHA256" \
        "$CORRECTNESS_MODE" "$TIMING_PROTOCOL" "$RUNS" "$TIMING_ESTIMATOR" "$((1 + PROFILE))" \
        "$OY_DUCKDB_TIMEOUT_SECS" "$OY_OUTERYAN_TIMEOUT_SECS" "$duckdb_status" "$outeryan_status" \
        "$duckdb_timeout_stage" "$outeryan_timeout_stage" "$duckdb_correctness_status" "$outeryan_correctness_status" \
        "$executed_round1_pairs" "$executed_round1_filters" "$executed_round2_pairs" "$executed_round2_filters"
}

# ==== Every query, once, under the fixed per-statement timeout =============
echo "Temporary result storage: $OY_RUN_TMPDIR" >&2
echo "Temporary filesystem: $OY_TMP_FREE available on $OY_TMP_MOUNT (base=$OY_TMPDIR)" >&2
echo "--- Per-query: decision + warm-up/profile/timing; correctness=$CORRECTNESS_MODE (TM=${OY_THREADS}) ---" >&2
for ((i=0; i<${#LABELS[@]}; i++)); do
    process_one "$i"
done

# ==== Final summary computed from the Q* arrays =============================
QN="${#LABELS[@]}"
NCORRECT=0; NUNCHECKED=0; NTIMED=0; NFALLBACK=0; NSKIP=0; NKBM=0; NKHASH=0; NKMIX=0
NNO=0; NYES=0; SUMNO=0; SUMYES=0
NBASELINE=0; NOUTERYAN=0; SUMBASELINE=0; SUMOUTERYAN=0
NSAME=0; NREJECT=0; NSELECTED=0; NDECISION_UNKNOWN=0; NGATE_APPLIED=0
for ((i=0; i<QN; i++)); do
    [ "${QGATE[i]}" = "1" ] && NGATE_APPLIED=$((NGATE_APPLIED+1))
    case "${QREORDERED[i]}:${QSELECTED[i]}" in
        0:0) NSAME=$((NSAME+1));;
        1:0) NREJECT=$((NREJECT+1));;
        0:1|1:1) NSELECTED=$((NSELECTED+1));;
        *)   NDECISION_UNKNOWN=$((NDECISION_UNKNOWN+1));;
    esac
    case "${QCORRECT[i]}" in
        TRUE) NCORRECT=$((NCORRECT+1));;
        NOT-CHECKED) NUNCHECKED=$((NUNCHECKED+1));;
    esac
    if [ "${QTIMING_STATUS[i]}" = "fallback-skip" ]; then
        NFALLBACK=$((NFALLBACK+1))
        continue
    fi
    case "${QCORRECT[i]}" in
        TRUE|NOT-CHECKED) ;;
        *) NSKIP=$((NSKIP+1)); continue;;
    esac
    [ "${QTIMING_STATUS[i]}" = "measured" ] && NTIMED=$((NTIMED+1))
    case "${QKER[i]}" in bitmap) NKBM=$((NKBM+1));; hash) NKHASH=$((NKHASH+1));; mixed) NKMIX=$((NKMIX+1));; esac
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
MNO="$(awk -v s="$SUMNO" -v n="$NNO" 'BEGIN{print (n? s/n : "-")}')"
MYES="$(awk -v s="$SUMYES" -v n="$NYES" 'BEGIN{print (n? s/n : "-")}')"
MBASELINE="$(awk -v s="$SUMBASELINE" -v n="$NBASELINE" 'BEGIN{print (n? s/n : "-")}')"
MOUTERYAN="$(awk -v s="$SUMOUTERYAN" -v n="$NOUTERYAN" 'BEGIN{print (n? s/n : "-")}')"
{
    echo
    echo "============================== SUMMARY ================================"
    echo "queries=$QN  correct=$NCORRECT  not-checked=$NUNCHECKED  fallback-skip=$NFALLBACK  incorrect/not-run=$NSKIP  timed=$NTIMED"
    echo "kernel (executed diagnostics): bitmap=$NKBM  hash=$NKHASH  mixed=$NKMIX"
    echo "threads: multi=${OY_THREADS}"
    echo "OuterYan decisions: same-grouping=$NSAME  changed-rejected=$NREJECT  selected=$NSELECTED  unknown=$NDECISION_UNKNOWN  cost-gate-applied=$NGATE_APPLIED"
    echo "coverage by relation count:"
    while IFS= read -r nrel; do
        [ -n "$nrel" ] || continue
        nrel_queries=0; nrel_correct=0; nrel_fallback=0; nrel_timed=0
        for ((i=0; i<QN; i++)); do
            [ "${QNREL[i]}" = "$nrel" ] || continue
            nrel_queries=$((nrel_queries+1))
            [ "${QCORRECT[i]}" != "TRUE" ] || nrel_correct=$((nrel_correct+1))
            if [ "${QTIMING_STATUS[i]}" = "fallback-skip" ]; then
                nrel_fallback=$((nrel_fallback+1))
                continue
            fi
            [ "${QTIMING_STATUS[i]}" = "measured" ] && nrel_timed=$((nrel_timed+1))
        done
        echo "  relations=$nrel  queries=$nrel_queries  correct=$nrel_correct  fallback-skip=$nrel_fallback  timed=$nrel_timed"
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
if [ "$PROFILE" = 1 ]; then
    if rmdir "$PROFILE_DIR" 2>/dev/null; then
        echo "No profile error artifacts retained"
    else
        echo "Partial/error profile artifacts retained in $PROFILE_DIR"
    fi
fi
if [ "$CAPTURE_PLANS" = 1 ]; then
    echo "Plan artifacts written to $PLAN_DIR"
fi
if [ "${OY_DEFER_STATISTICS:-0}" != 1 ]; then
    STATISTICS_DIR="${OUT%.txt}_statistics"
    if "${PYTHON_BIN:-python3}" "$SCRIPT_DIR/gen_experiment_result.py" --statistics-only \
        --output-dir "$STATISTICS_DIR" --run "$EXPERIMENT_GROUP" "$CSV_FINAL"; then
        echo "Statistics written to $STATISTICS_DIR"
    else
        echo "Failed to generate statistics from $CSV_FINAL" >&2
        exit 1
    fi
fi
echo "RESULT_TXT=$OUT"
echo "RESULT_CSV=$CSV_FINAL"
if [ "${OY_DEFER_STATISTICS:-0}" != 1 ]; then
    echo "RESULT_STATISTICS_DIR=$STATISTICS_DIR"
fi
if [ "$CAPTURE_PLANS" = 1 ]; then
    echo "RESULT_PLAN_DIR=$PLAN_DIR"
fi
