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
#   4. Run core and industry-inspired experiments into separate result files
#
# Environment overrides (all optional):
#   GRAPH_DATASET    bitcoin (default) | epinions | google | wiki | dblp
#   TPCH_SF          TPC-H scale factor (default 100)
#   TPCDS_SF         TPC-DS scale factor (default 100)
#   OY_THREADS       Multi-thread profile/timing count (default 48)
#   OY_RUNS          Timed iterations per config (default 3, median taken)
#   JOBS             Make parallelism (default: nproc)
#   SKIP_BUILD       Set to 1 to skip compilation (use existing binary)
#   SKIP_DATA        Set to 1 to skip database generation
#   SKIP_QUERY_GEN   Set to 1 to keep the existing generated benchmark
#   RUN_INDUSTRY     Set to 0 to skip industry-inspired queries (default 1)
#   RUN_SUPPLEMENTAL Set to 1 to run performance-selected stress queries
#   OY_CORPUS        When set, run only this custom corpus (legacy behavior)
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

RUN_TS="$(date '+%Y%m%d_%H%M%S')"
mkdir -p "$SCRIPT_DIR/results"
RUN_LOG="$SCRIPT_DIR/results/run_all_${RUN_TS}.log"

# --- Helpers -----------------------------------------------------------------
log() { printf '\n\033[1;36m===> %s\033[0m\n' "$*"; }
err() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
elapsed() { local s=$1; printf '%dm%02ds' $((s/60)) $((s%60)); }

START_TIME=$SECONDS
EXPERIMENT_ARGS=("$@")
RESULT_TXTS=()
RUN_INDUSTRY="${RUN_INDUSTRY:-1}"
RUN_SUPPLEMENTAL="${RUN_SUPPLEMENTAL:-0}"
CUSTOM_CORPUS="${OY_CORPUS:-}"

# --- Step 1: Compile ---------------------------------------------------------
if [ "${SKIP_BUILD:-0}" != "1" ]; then
    log "Step 1/4: Building DuckDB release (BUILD_TPCH=1 BUILD_TPCDS=1)"
    JOBS="${JOBS:-$(nproc 2>/dev/null || echo 8)}"
    BUILD_TPCH=1 BUILD_TPCDS=1 make release -j"$JOBS" 2>&1 | tee -a "$RUN_LOG"
    log "Build complete ($(elapsed $((SECONDS - START_TIME))))"
else
    log "Step 1/4: Skipping build (SKIP_BUILD=1)"
fi

DUCKDB_BIN="$REPO_ROOT/build/release/duckdb"
[ -x "$DUCKDB_BIN" ] || err "Binary not found: $DUCKDB_BIN. Run without SKIP_BUILD=1."
export DUCKDB_BIN

# --- Step 2: Build databases -------------------------------------------------
if [ "${SKIP_DATA:-0}" != "1" ]; then
    log "Step 2/4: Building required databases"
    STEP2_START=$SECONDS
    if [ -n "$CUSTOM_CORPUS" ] || [ "$RUN_SUPPLEMENTAL" = "1" ]; then
        bash "$SCRIPT_DIR/build_db.sh" all 2>&1 | tee -a "$RUN_LOG"
    else
        bash "$SCRIPT_DIR/build_db.sh" tpch tpcds job 2>&1 | tee -a "$RUN_LOG"
    fi
    log "Databases ready ($(elapsed $((SECONDS - STEP2_START))))"
else
    log "Step 2/4: Skipping data build (SKIP_DATA=1)"
fi

# --- Step 3: Generate benchmark ---------------------------------------------
if [ "${SKIP_QUERY_GEN:-0}" != "1" ]; then
    log "Step 3/4: Regenerating benchmark queries and manifests"
    python3 "$SCRIPT_DIR/gen_outerjoin_benchmark.py" 2>&1 | tee -a "$RUN_LOG"
else
    log "Step 3/4: Skipping benchmark generation (SKIP_QUERY_GEN=1)"
fi

# --- Step 4: Run experiments -------------------------------------------------
run_experiment() {
    local label="$1" corpus="$2" default_only="$3" out
    out="$SCRIPT_DIR/results/experiment_onoff_${label}_${RUN_TS}.txt"
    log "Step 4/4: Running $label on/off experiment"
    OY_CORPUS="$corpus" bash "$SCRIPT_DIR/experiment_onoff.sh" \
        --only "$default_only" "${EXPERIMENT_ARGS[@]}" -o "$out" \
        2>&1 | tee -a "$RUN_LOG"
    RESULT_TXTS+=("$out")
}

STEP4_START=$SECONDS
if [ -n "$CUSTOM_CORPUS" ]; then
    run_experiment "custom" "$CUSTOM_CORPUS" "all"
else
    run_experiment "core" "$SCRIPT_DIR/outerjoin_benchmark/core" "bench"
    if [ "$RUN_INDUSTRY" = "1" ]; then
        run_experiment "industry_inspired" \
            "$SCRIPT_DIR/outerjoin_benchmark/industry_inspired" "bench"
    fi
    if [ "$RUN_SUPPLEMENTAL" = "1" ]; then
        run_experiment "supplemental" \
            "$SCRIPT_DIR/outerjoin_benchmark/supplemental" "all"
    fi
fi
log "Experiments complete ($(elapsed $((SECONDS - STEP4_START))))"

# --- Summary -----------------------------------------------------------------
TOTAL=$((SECONDS - START_TIME))
log "All done! Total time: $(elapsed $TOTAL)"
echo "Run log: $RUN_LOG"
for result_txt in "${RESULT_TXTS[@]}"; do
    echo "Results TXT: $result_txt"
    echo "Final CSV: ${result_txt%.txt}.csv"
    echo "Attempts CSV: ${result_txt%.txt}.attempts.csv"
    if [ -d "${result_txt%.txt}.plans" ]; then
        echo "Plan artifacts: ${result_txt%.txt}.plans"
    fi
done
