#!/usr/bin/env bash
# ============================================================================
# run_all.sh — One-shot script: build + data + experiment (Linux server)
#
# Assumes the repo is already cloned. Run from the repo root:
#   bash auto_test/run_all.sh [--query-type all|join|graph|aggregate]
#
# What it does:
#   1. Compile DuckDB release with required extensions (tpch, tpcds)
#   2. Build the databases required by the selected benchmark strata
#   3. Regenerate the benchmark and provenance manifests
#   4. Run the Original/OuterYan bare-query comparison for the corpus
#
# Environment overrides (all optional):
#   GRAPH_DATASET    bitcoin (default) | epinions | google | wiki | dblp
#   TPCH_SF          TPC-H scale factor (default 100)
#   TPCDS_SF         TPC-DS scale factor (default 50)
#   OY_THREAD_COUNTS Sequential timing counts (default "32")
#   OY_THREADS       Override with one multi-thread timing count
#   OY_PROFILE       Separate ON phase-profile batch (default 1; set 0 to skip)
#   --threads LIST   CLI override, e.g. "16 32" or 16,32
#   OY_RUNS          Timed iterations after one warm-up (default 3)
#   OY_TIMEOUT_SECS  Per-statement timeout seconds (default 600; 10 minutes)
#   --timeout S      CLI timeout override; 0 disables the timeout
#   JOBS             Make parallelism (default: nproc)
#   PYTHON_BIN       Python 3.7+ interpreter (default: python3; may be repo-local)
#   SKIP_BUILD       Set to 1 to skip compilation (use existing binary)
#   SKIP_DATA        Set to 1 to skip target DuckDB database generation
#   SKIP_QUERY_GEN   Set to 1 to keep the existing generated benchmark
#   --query-type T   all (default), join, graph, or aggregate
#   --all            Alias for the full deduplicated corpus
#   OY_CORPUS        Custom corpus for the default two-way mode
#
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# configs.sh supplies DuckDB paths and timing defaults. Capture
# the caller's corpus first: configs.sh also assigns the normal corpus default,
# which must not accidentally activate run_all's custom-corpus mode.
CALLER_OY_CORPUS="${OY_CORPUS:-}"
CALLER_DUCKDB_BIN="${DUCKDB_BIN:-}"
. "$SCRIPT_DIR/configs.sh"
. "$SCRIPT_DIR/thread_sweep.sh"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHON_BIN

cd "$REPO_ROOT"

RUN_TS="$(date '+%Y%m%d_%H%M%S')"
mkdir -p "$SCRIPT_DIR/results"
RUN_LOG="$SCRIPT_DIR/results/run_all_${RUN_TS}.log"

# --- Helpers -----------------------------------------------------------------
log() { printf '\n\033[1;36m===> %s\033[0m\n' "$*"; }
err() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
elapsed() { local s=$1; printf '%dm%02ds' $((s/60)) $((s%60)); }

if [[ "$PYTHON_BIN" == */* ]]; then
    [ -x "$PYTHON_BIN" ] || err "Python binary is not executable: $PYTHON_BIN"
else
    command -v "$PYTHON_BIN" >/dev/null 2>&1 || err "Python binary was not found: $PYTHON_BIN"
fi
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 7) else 1)' || \
    err "Python 3.7 or newer is required: $PYTHON_BIN"

# Fail early for retired workflow requests instead of running a different comparison.
if [ "${RUN_PGPLAN:-${RUN_PG_REPLAY:-0}}" != 0 ]; then
    err "PGPlan workflow has been removed; unset RUN_PGPLAN/RUN_PG_REPLAY to run Original/OuterYan"
fi

START_TIME=$SECONDS
RAW_EXPERIMENT_ARGS=("$@")
EXPERIMENT_ARGS=(--query-type all)
RESULT_TXTS=()
RUN_STATUS=0
CUSTOM_CORPUS="$CALLER_OY_CORPUS"
THREAD_COUNTS="${OY_THREAD_COUNTS:-$OY_THREADS}"

# The built-in corpus is already deduplicated; selection is by query type.
argument_index=0
while [ "$argument_index" -lt "${#RAW_EXPERIMENT_ARGS[@]}" ]; do
    argument="${RAW_EXPERIMENT_ARGS[$argument_index]}"
    case "$argument" in
        --version|--corpus-version)
            err "Version selection is retired; use --query-type join, graph, or aggregate";;
        --threads)
            [ "$((argument_index + 1))" -lt "${#RAW_EXPERIMENT_ARGS[@]}" ] || err "--threads requires a value"
            THREAD_COUNTS="${RAW_EXPERIMENT_ARGS[$((argument_index + 1))]}"
            EXPERIMENT_ARGS+=("$argument" "$THREAD_COUNTS")
            argument_index=$((argument_index + 2));;
        *)
            EXPERIMENT_ARGS+=("$argument")
            argument_index=$((argument_index + 1));;
    esac
done
oy_parse_thread_counts "$THREAD_COUNTS" || exit $?

# --- Step 1: Compile ---------------------------------------------------------
if [ "${SKIP_BUILD:-0}" != "1" ]; then
    log "Step 1/4: Building DuckDB release (BUILD_TPCH=1 BUILD_TPCDS=1)"
    JOBS="${JOBS:-$(nproc 2>/dev/null || echo 8)}"
    BUILD_TPCH=1 BUILD_TPCDS=1 make release -j"$JOBS" 2>&1 | tee -a "$RUN_LOG"
    log "Build complete ($(elapsed $((SECONDS - START_TIME))))"
else
    log "Step 1/4: Skipping build (SKIP_BUILD=1)"
fi

# If this invocation built release and the caller did not select a binary,
# prefer the just-built release even when configs.sh initially fell back to a
# pre-existing debug binary.
if [ "${SKIP_BUILD:-0}" != "1" ] && [ -z "$CALLER_DUCKDB_BIN" ] && \
        [ "$DUCKDB_BIN" = "$REPO_ROOT/build/debug/duckdb" ]; then
    DUCKDB_BIN="$REPO_ROOT/build/release/duckdb"
fi
[ -x "$DUCKDB_BIN" ] || err "Binary not found: $DUCKDB_BIN. Build it or set DUCKDB_BIN in auto_test/configs.sh."
export DUCKDB_BIN

# --- Step 2: Build databases -------------------------------------------------
if [ "${SKIP_DATA:-0}" != "1" ]; then
    log "Step 2/4: Building required databases"
    STEP2_START=$SECONDS
    bash "$SCRIPT_DIR/build_db.sh" all 2>&1 | tee -a "$RUN_LOG"
    log "Databases ready ($(elapsed $((SECONDS - STEP2_START))))"
else
    log "Step 2/4: Skipping data build (SKIP_DATA=1)"
fi

# --- Step 3: Generate benchmark ---------------------------------------------
if [ "${SKIP_QUERY_GEN:-0}" != "1" ]; then
    log "Step 3/4: Regenerating the deduplicated benchmark"
    "$PYTHON_BIN" "$SCRIPT_DIR/gen_outerjoin_benchmark.py" 2>&1 | tee -a "$RUN_LOG"
else
    log "Step 3/4: Skipping benchmark generation (SKIP_QUERY_GEN=1)"
fi

# --- Step 4: Run corpus experiments -----------------------------------------
run_experiment() {
    local label="$1" corpus="$2" default_only="$3" out experiment_status=0
    out="$SCRIPT_DIR/results/experiment_onoff_${label}_${RUN_TS}_t${OY_THREADS}.txt"
    log "Step 4/4: Running $label on/off experiment (threads=$OY_THREADS)"
    if [ -n "$corpus" ]; then
        if OY_CORPUS="$corpus" bash "$SCRIPT_DIR/experiment_onoff.sh" \
            --only "$default_only" "${EXPERIMENT_ARGS[@]}" --threads "$OY_THREADS" -o "$out" \
            2>&1 | tee -a "$RUN_LOG"; then
            :
        else
            experiment_status=$?
        fi
    else
        if env -u OY_CORPUS -u OY_CORPUS_VERSION -u OY_CORPUS_SCOPE \
            bash "$SCRIPT_DIR/experiment_onoff.sh" \
            --only "$default_only" "${EXPERIMENT_ARGS[@]}" --threads "$OY_THREADS" -o "$out" \
            2>&1 | tee -a "$RUN_LOG"; then
            :
        else
            experiment_status=$?
        fi
    fi
    RESULT_TXTS+=("$out")
    return "$experiment_status"
}

STEP4_START=$SECONDS
for thread_count in "${OY_THREAD_VALUES[@]}"; do
    export OY_THREADS="$thread_count" OY_THREAD_COUNTS="$thread_count"
    log "Multi-thread configuration: threads=$thread_count"
    thread_status=0
    if [ -n "$CUSTOM_CORPUS" ]; then
        run_experiment "custom" "$CUSTOM_CORPUS" "all" || thread_status=$?
    else
        run_experiment "benchmark" "" "all" || thread_status=$?
    fi
    case "$thread_status" in
        130|143) exit "$thread_status";;
        0) ;;
        *) RUN_STATUS="$thread_status";;
    esac
done
log "Experiments complete ($(elapsed $((SECONDS - STEP4_START))))"

# --- Summary -----------------------------------------------------------------
TOTAL=$((SECONDS - START_TIME))
if [ "$RUN_STATUS" -eq 0 ]; then
    log "All done! Total time: $(elapsed $TOTAL)"
else
    log "Comparison corpus finished with failures (exit status $RUN_STATUS; total time: $(elapsed $TOTAL))"
fi
echo "Run log: $RUN_LOG"
if [ "${#RESULT_TXTS[@]}" -gt 0 ]; then
    for result_txt in "${RESULT_TXTS[@]}"; do
        echo "Results TXT: $result_txt"
        echo "Final CSV: ${result_txt%.txt}.csv"
        echo "Statistics: ${result_txt%.txt}_statistics/"
        if [ -d "${result_txt%.txt}.plans" ]; then
            echo "Plan artifacts: ${result_txt%.txt}.plans"
        fi
    done
fi
# Preserve the corpus helper's failure status, but only after handing all
# generated status, timing, and failure-report paths back to the caller.
if [ "$RUN_STATUS" -ne 0 ]; then
    exit "$RUN_STATUS"
fi
