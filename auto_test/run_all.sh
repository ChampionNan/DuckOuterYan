#!/usr/bin/env bash
# ============================================================================
# run_all.sh — One-shot script: build + data + experiment (Linux server)
#
# Assumes the repo is already cloned. Run from the repo root:
#   bash auto_test/run_all.sh
#
# What it does:
#   1. Compile DuckDB release with required extensions (tpch, tpcds)
#   2. Build the databases required by the selected benchmark strata
#   3. Regenerate the benchmark and provenance manifests
#   4. Skip PostgreSQL work by default
#   5. Run the Original/OuterYan bare-query comparison for the corpus
#
# Environment overrides (all optional):
#   GRAPH_DATASET    bitcoin (default) | epinions | google | wiki | dblp
#   TPCH_SF          TPC-H scale factor (default 100)
#   TPCDS_SF         TPC-DS scale factor (default 100)
#   OY_THREAD_COUNTS Sequential timing counts (default "16 32")
#   OY_THREADS       Override with one multi-thread timing count
#   --threads LIST   CLI override, e.g. "16 32" or 16,32
#   OY_RUNS          Legacy timed iterations and PGPLAN_RUNS fallback (default 3)
#   PGPLAN_RUNS      PGPlan TM measured iterations (default OY_RUNS)
#   JOBS             Make parallelism (default: nproc)
#   PYTHON_BIN       Python 3.7+ interpreter (default: python3; may be repo-local)
#   SKIP_BUILD       Set to 1 to skip compilation (use existing binary)
#   SKIP_DATA        Set to 1 to skip target DuckDB database generation
#   SKIP_QUERY_GEN   Set to 1 to keep the existing generated benchmark
#   RUN_PGPLAN       Set to 1 to opt into PGPlan generation/testing (default 0)
#   PGPLAN_SETUP     source (default, auto-installs) | docker | external
#   SKIP_PG_DATA     Set to 1 to require existing exact TPC-H SF0.01 data
#   PGPLAN_CORPUS    PGPlan corpus root (default: outerjoin_query, 185 queries)
#   PGPLAN_SAMPLE_ROWS  Per-table graph/TPC-DS/JOB plan sample (default 1000)
#   PGPLAN_PLAN_CACHE  Persistent typed-plan cache (default auto_test/pgplan/plans)
#   PGPLAN_COMPARISON_MODE  both (default) | pgplan-only | none
#   --comparison-mode MODE  CLI equivalent
#   --skip1          Alias for --comparison-mode pgplan-only
#   --skip2, --performance-only, --performance_only, --performace_only
#                    Aliases for --comparison-mode none
#   PGPLAN_CORRECTNESS_MODE  target (default) | bounded | reuse
#   PGPLAN_CORRECTNESS_FROM  Prior target-mode corpus root required by reuse
#   PGPLAN_REUSE_FROM  One-parameter prior corpus for plan+correctness reuse
#   --reuse-from DIR  CLI equivalent; automatically sets all three SKIP_* flags
#   PGPLAN_CORRECTNESS_GRAPH_ROWS  Bounded-mode graph prefix (default 500)
#   PGPLAN_CORRECTNESS_JOB_ROWS  Bounded-mode JOB prefix (default 1000)
#   PGPLAN_CORRECTNESS_MAX_RESULT_ROWS  Bounded-mode result cap (default 2000000)
#   PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS  Bounded-mode preflight limit (default 30)
#   PGPLAN_CAPTURE_TIMEOUT_SECS  Plain PG EXPLAIN limit (default 300)
#   PGPLAN_TIMEOUT_SECS  DuckDB/per-postprocess step limit (default 1800)
#   OY_CORPUS        Custom corpus for the default two-way mode
#
# Docker is optional. With no PostgreSQL override, source mode downloads,
# verifies, builds, installs, initializes, and starts PostgreSQL 16.2 under the
# repository when the managed installation is absent.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# configs.sh supplies all DuckDB/PostgreSQL paths and timing defaults. Capture
# the caller's corpus first: configs.sh also assigns the normal corpus default,
# which must not accidentally activate run_all's custom-corpus mode.
CALLER_OY_CORPUS="${OY_CORPUS:-}"
CALLER_DUCKDB_BIN="${DUCKDB_BIN:-}"
CALLER_PGPLAN_THREADS="${PGPLAN_THREADS:-${PG_REPLAY_THREADS:-}}"
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

START_TIME=$SECONDS
EXPERIMENT_ARGS=("$@")
RESULT_TXTS=()
PGPLAN_RESULT_DIRS=()
RUN_STATUS=0
RUN_PGPLAN="${RUN_PGPLAN:-${RUN_PG_REPLAY:-0}}"
CUSTOM_CORPUS="$CALLER_OY_CORPUS"
REUSE_SHORTCUT_FROM="${PGPLAN_REUSE_FROM:-}"
THREAD_COUNTS="${OY_THREAD_COUNTS:-$OY_THREADS}"
if [ "$RUN_PGPLAN" = 1 ] && [ -n "$CALLER_PGPLAN_THREADS" ]; then
    THREAD_COUNTS="$CALLER_PGPLAN_THREADS"
fi
argument_index=0
while [ "$argument_index" -lt "${#EXPERIMENT_ARGS[@]}" ]; do
    if [ "${EXPERIMENT_ARGS[$argument_index]}" = "--threads" ]; then
        [ "$((argument_index + 1))" -lt "${#EXPERIMENT_ARGS[@]}" ] || err "--threads requires a value"
        THREAD_COUNTS="${EXPERIMENT_ARGS[$((argument_index + 1))]}"
        argument_index=$((argument_index + 2))
    elif [ "${EXPERIMENT_ARGS[$argument_index]}" = "--reuse-from" ]; then
        [ "$((argument_index + 1))" -lt "${#EXPERIMENT_ARGS[@]}" ] || \
            err "--reuse-from requires a prior corpus directory"
        REUSE_SHORTCUT_FROM="${EXPERIMENT_ARGS[$((argument_index + 1))]}"
        argument_index=$((argument_index + 2))
    else
        argument_index=$((argument_index + 1))
    fi
done
oy_parse_thread_counts "$THREAD_COUNTS" || exit $?
if [ -n "$REUSE_SHORTCUT_FROM" ]; then
    for skip_name in SKIP_BUILD SKIP_DATA SKIP_QUERY_GEN; do
        if [ "${!skip_name+x}" = "x" ] && [ "${!skip_name}" != "1" ]; then
            err "$skip_name=${!skip_name} conflicts with --reuse-from; reuse requires the existing binary, databases, and query bytes"
        fi
        printf -v "$skip_name" '%s' 1
        export "$skip_name"
    done
    log "Reuse mode: preserving existing DuckDB binary, databases, and queries from the sealed run inputs"
fi

case "$RUN_PGPLAN" in
    0|1) ;;
    *) err "RUN_PGPLAN must be 0 or 1 (got: $RUN_PGPLAN)" ;;
esac

# --- Step 1: Compile ---------------------------------------------------------
if [ "${SKIP_BUILD:-0}" != "1" ]; then
    log "Step 1/5: Building DuckDB release (BUILD_TPCH=1 BUILD_TPCDS=1)"
    JOBS="${JOBS:-$(nproc 2>/dev/null || echo 8)}"
    BUILD_TPCH=1 BUILD_TPCDS=1 make release -j"$JOBS" 2>&1 | tee -a "$RUN_LOG"
    log "Build complete ($(elapsed $((SECONDS - START_TIME))))"
else
    log "Step 1/5: Skipping build (SKIP_BUILD=1)"
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
    log "Step 2/5: Building required databases"
    STEP2_START=$SECONDS
    bash "$SCRIPT_DIR/build_db.sh" all 2>&1 | tee -a "$RUN_LOG"
    log "Databases ready ($(elapsed $((SECONDS - STEP2_START))))"
else
    log "Step 2/5: Skipping data build (SKIP_DATA=1)"
fi

# --- Step 3: Generate benchmark ---------------------------------------------
if [ "${SKIP_QUERY_GEN:-0}" != "1" ]; then
    log "Step 3/5: Regenerating benchmark queries and manifests"
    "$PYTHON_BIN" "$SCRIPT_DIR/gen_outerjoin_benchmark.py" 2>&1 | tee -a "$RUN_LOG"
else
    log "Step 3/5: Skipping benchmark generation (SKIP_QUERY_GEN=1)"
fi

# --- Step 4/5: PostgreSQL-backed comparison corpus ---------------------------
run_pgplan_corpus() {
    local corpus out_dir corpus_status=0 argument_index=0
    local correctness_mode correctness_from reuse_from comparison_mode plan_cache
    local -a corpus_command
    corpus="${PGPLAN_CORPUS:-${CUSTOM_CORPUS:-$SCRIPT_DIR/outerjoin_query}}"
    out_dir="${PGPLAN_OUT:-$SCRIPT_DIR/results/pgplan_corpus_${RUN_TS}}"
    correctness_mode="${PGPLAN_CORRECTNESS_MODE:-target}"
    correctness_from="${PGPLAN_CORRECTNESS_FROM:-}"
    reuse_from="${PGPLAN_REUSE_FROM:-}"
    comparison_mode="${PGPLAN_COMPARISON_MODE:-both}"
    plan_cache="${PGPLAN_PLAN_CACHE:-$SCRIPT_DIR/pgplan/plans}"
    [ -x "$SCRIPT_DIR/pgplan/corpus_experiment.sh" ] || \
        err "PGPlan corpus helper not found: $SCRIPT_DIR/pgplan/corpus_experiment.sh"

    # Forwarded corpus arguments follow the defaults below, so their last
    # --out value wins. Track that same location for the final handoff.
    while [ "$argument_index" -lt "${#EXPERIMENT_ARGS[@]}" ]; do
        case "${EXPERIMENT_ARGS[$argument_index]}" in
            --out)
                if [ "$((argument_index + 1))" -lt "${#EXPERIMENT_ARGS[@]}" ]; then
                    out_dir="${EXPERIMENT_ARGS[$((argument_index + 1))]}"
                    argument_index=$((argument_index + 2))
                else
                    argument_index=$((argument_index + 1))
                fi
                ;;
            --correctness-mode)
                if [ "$((argument_index + 1))" -lt "${#EXPERIMENT_ARGS[@]}" ]; then
                    correctness_mode="${EXPERIMENT_ARGS[$((argument_index + 1))]}"
                    argument_index=$((argument_index + 2))
                else
                    argument_index=$((argument_index + 1))
                fi
                ;;
            --correctness-from)
                if [ "$((argument_index + 1))" -lt "${#EXPERIMENT_ARGS[@]}" ]; then
                    correctness_from="${EXPERIMENT_ARGS[$((argument_index + 1))]}"
                    argument_index=$((argument_index + 2))
                else
                    argument_index=$((argument_index + 1))
                fi
                ;;
            --reuse-from)
                if [ "$((argument_index + 1))" -lt "${#EXPERIMENT_ARGS[@]}" ]; then
                    reuse_from="${EXPERIMENT_ARGS[$((argument_index + 1))]}"
                    correctness_mode="reuse"
                    correctness_from="$reuse_from"
                    argument_index=$((argument_index + 2))
                else
                    argument_index=$((argument_index + 1))
                fi
                ;;
            --comparison-mode)
                if [ "$((argument_index + 1))" -lt "${#EXPERIMENT_ARGS[@]}" ]; then
                    comparison_mode="${EXPERIMENT_ARGS[$((argument_index + 1))]}"
                    argument_index=$((argument_index + 2))
                else
                    argument_index=$((argument_index + 1))
                fi
                ;;
            --skip1)
                comparison_mode="pgplan-only"
                argument_index=$((argument_index + 1))
                ;;
            --skip2|--performance-only|--performance_only|--performace_only)
                comparison_mode="none"
                argument_index=$((argument_index + 1))
                ;;
            --plan-cache)
                if [ "$((argument_index + 1))" -lt "${#EXPERIMENT_ARGS[@]}" ]; then
                    plan_cache="${EXPERIMENT_ARGS[$((argument_index + 1))]}"
                    argument_index=$((argument_index + 2))
                else
                    argument_index=$((argument_index + 1))
                fi
                ;;
            *) argument_index=$((argument_index + 1)) ;;
        esac
    done
    if [ -n "$reuse_from" ]; then
        correctness_mode="reuse"
        correctness_from="$reuse_from"
    fi
    if [ "${#OY_THREAD_VALUES[@]}" -gt 1 ]; then
        out_dir="${out_dir}_t${OY_THREADS}"
    fi

    # Record the handoff location before running the corpus. The corpus returns
    # nonzero when any query fails, but its status and aggregate reports are
    # still the useful output of the completed comparison experiment.
    PGPLAN_RESULT_DIRS+=("$out_dir")

    corpus_command=(
        bash "$SCRIPT_DIR/pgplan/corpus_experiment.sh"
        --corpus "$corpus"
        --duckdb-bin "$DUCKDB_BIN"
        --pg-dsn "$PG_DSN"
        --rows "${PGPLAN_SAMPLE_ROWS:-1000}"
        --threads "${PGPLAN_THREADS:-${OY_THREADS:-1}}"
        --correctness-mode "${PGPLAN_CORRECTNESS_MODE:-target}"
        --comparison-mode "${PGPLAN_COMPARISON_MODE:-both}"
        --plan-cache "${PGPLAN_PLAN_CACHE:-$SCRIPT_DIR/pgplan/plans}"
        --out "$out_dir"
    )
    if [ -n "${PGPLAN_CORRECTNESS_FROM:-}" ]; then
        corpus_command+=(--correctness-from "$PGPLAN_CORRECTNESS_FROM")
    fi
    if [ -n "${PGPLAN_REUSE_FROM:-}" ]; then
        corpus_command+=(--reuse-from "$PGPLAN_REUSE_FROM")
    fi
    if [ "${#EXPERIMENT_ARGS[@]}" -gt 0 ]; then
        corpus_command+=("${EXPERIMENT_ARGS[@]}")
    fi
    corpus_command+=(--threads "$OY_THREADS" --out "$out_dir")

    if [ "$comparison_mode" = "none" ]; then
        log "Step 4/5: Checking the persistent PGPlan cache and preparing cache misses (correctness disabled)"
    elif [ "$comparison_mode" = "pgplan-only" ]; then
        log "Step 4/5: Checking the persistent PGPlan cache and preparing Original-versus-PGPlan correctness"
    else
        case "$correctness_mode" in
            bounded)
                log "Step 4/5: Checking the persistent PGPlan cache and preparing bounded correctness databases"
                ;;
            reuse)
                if [ -n "$reuse_from" ]; then
                    log "Step 4/5: Reusing PGPlan artifacts and sealed target correctness from $reuse_from (PostgreSQL setup skipped)"
                else
                    log "Step 4/5: Checking the persistent PGPlan cache (reusing sealed target correctness from $correctness_from)"
                fi
                ;;
            *)
                log "Step 4/5: Checking the persistent PGPlan cache and preparing exact target-data comparisons"
                ;;
        esac
    fi
    log "Step 5/5: Comparison mode=$comparison_mode across $corpus (plan cache: $plan_cache)"
    if "${corpus_command[@]}" 2>&1 | tee -a "$RUN_LOG"; then
        corpus_status=0
    else
        corpus_status=$?
    fi
    return "$corpus_status"
}

# --- Step 5: Run corpus experiments -----------------------------------------
run_experiment() {
    local label="$1" corpus="$2" default_only="$3" out experiment_status=0
    out="$SCRIPT_DIR/results/experiment_onoff_${label}_${RUN_TS}_t${OY_THREADS}.txt"
    log "Step 5/5: Running $label on/off experiment (threads=$OY_THREADS)"
    if OY_CORPUS="$corpus" bash "$SCRIPT_DIR/experiment_onoff.sh" \
        --only "$default_only" "${EXPERIMENT_ARGS[@]}" --threads "$OY_THREADS" -o "$out" \
        2>&1 | tee -a "$RUN_LOG"; then
        :
    else
        experiment_status=$?
    fi
    RESULT_TXTS+=("$out")
    return "$experiment_status"
}

STEP4_START=$SECONDS
for thread_count in "${OY_THREAD_VALUES[@]}"; do
    export OY_THREADS="$thread_count" OY_THREAD_COUNTS="$thread_count"
    export PGPLAN_THREADS="$thread_count" PG_REPLAY_THREADS="$thread_count"
    log "Multi-thread configuration: threads=$thread_count"
    thread_status=0
    if [ "$RUN_PGPLAN" = "1" ]; then
        run_pgplan_corpus || thread_status=$?
    elif [ -n "$CUSTOM_CORPUS" ]; then
        log "Step 4/5: PGPlan disabled; running default Original/OuterYan workflow"
        run_experiment "custom" "$CUSTOM_CORPUS" "all" || thread_status=$?
    else
        log "Step 4/5: PGPlan disabled; running default Original/OuterYan workflow"
        run_experiment "benchmark" "$SCRIPT_DIR/outerjoin_query" "all" || thread_status=$?
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
        echo "Attempts CSV: ${result_txt%.txt}.attempts.csv"
        if [ -d "${result_txt%.txt}.plans" ]; then
            echo "Plan artifacts: ${result_txt%.txt}.plans"
        fi
    done
fi
if [ "$RUN_PGPLAN" = "1" ]; then
    if [ "${#PGPLAN_RESULT_DIRS[@]}" -gt 0 ]; then
        for result_dir in "${PGPLAN_RESULT_DIRS[@]}"; do
            echo "Comparison result directory: $result_dir"
            echo "Comparison status TSV: $result_dir/status.tsv"
            echo "Comparison TSV: $result_dir/comparison.tsv"
            echo "Comparison CSV: $result_dir/comparison.csv"
            echo "Comparison detailed log: $result_dir/comparison.log"
            echo "Comparison summary TSV: $result_dir/summary.tsv"
            echo "Comparison failures TSV: $result_dir/failures.tsv"
            echo "Comparison plan artifacts: $result_dir/artifacts"
        done
    fi
fi

# Preserve the corpus helper's failure status, but only after handing all
# generated status, timing, and failure-report paths back to the caller.
if [ "$RUN_STATUS" -ne 0 ]; then
    exit "$RUN_STATUS"
fi
