#!/usr/bin/env bash
# ============================================================================
# run_all.sh — One-shot script: build + data + experiment (Linux server)
#
# Assumes the repo is already cloned. Run from the repo root:
#   bash auto_test/run_all.sh
#
# What it does:
#   1. Compile DuckDB release with required extensions (tpch, tpcds)
#   2. Build all databases (graph, tpch SF=100, tpcds SF=100, local JOB parquet)
#   3. Run the full on/off experiment (correctness + dual-thread timing)
#
# Environment overrides (all optional):
#   GRAPH_DATASET    bitcoin (default) | epinions | google | wiki | dblp
#   TPCH_SF          TPC-H scale factor (default 100)
#   TPCDS_SF         TPC-DS scale factor (default 100)
#   OY_THREADS       Multi-thread count (default 64)
#   OY_RUNS          Timed iterations per config (default 10, median taken)
#   JOBS             Make parallelism (default: nproc)
#   SKIP_BUILD       Set to 1 to skip compilation (use existing binary)
#   SKIP_DATA        Set to 1 to skip database generation
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

# --- Step 1: Compile ---------------------------------------------------------
if [ "${SKIP_BUILD:-0}" != "1" ]; then
    log "Step 1/3: Building DuckDB release (BUILD_TPCH=1 BUILD_TPCDS=1)"
    JOBS="${JOBS:-$(nproc 2>/dev/null || echo 8)}"
    BUILD_TPCH=1 BUILD_TPCDS=1 make release -j"$JOBS" 2>&1 | tee -a "$RUN_LOG"
    log "Build complete ($(elapsed $((SECONDS - START_TIME))))"
else
    log "Step 1/3: Skipping build (SKIP_BUILD=1)"
fi

DUCKDB_BIN="$REPO_ROOT/build/release/duckdb"
[ -x "$DUCKDB_BIN" ] || err "Binary not found: $DUCKDB_BIN. Run without SKIP_BUILD=1."
export DUCKDB_BIN

# --- Step 2: Build databases -------------------------------------------------
if [ "${SKIP_DATA:-0}" != "1" ]; then
    log "Step 2/3: Building all databases"
    STEP2_START=$SECONDS
    bash "$SCRIPT_DIR/build_db.sh" all 2>&1 | tee -a "$RUN_LOG"
    log "Databases ready ($(elapsed $((SECONDS - STEP2_START))))"
else
    log "Step 2/3: Skipping data build (SKIP_DATA=1)"
fi

# --- Step 3: Run experiment --------------------------------------------------
log "Step 3/3: Running on/off experiment"
STEP3_START=$SECONDS
bash "$SCRIPT_DIR/experiment_onoff.sh" "$@" 2>&1 | tee -a "$RUN_LOG"
log "Experiment complete ($(elapsed $((SECONDS - STEP3_START))))"

# --- Summary -----------------------------------------------------------------
TOTAL=$((SECONDS - START_TIME))
log "All done! Total time: $(elapsed $TOTAL)"
LATEST_TXT="$(ls -t "$SCRIPT_DIR/results"/experiment_onoff_*.txt 2>/dev/null | head -1)"
echo "Run log: $RUN_LOG"
if [ -n "$LATEST_TXT" ]; then
    echo "Results TXT: $LATEST_TXT"
    echo "Final CSV: ${LATEST_TXT%.txt}.csv"
    echo "Attempts CSV: ${LATEST_TXT%.txt}.attempts.csv"
    if [ -d "${LATEST_TXT%.txt}.plans" ]; then
        echo "Plan artifacts: ${LATEST_TXT%.txt}.plans"
    fi
fi
