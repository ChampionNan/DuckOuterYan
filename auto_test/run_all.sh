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
#   4. Prepare PostgreSQL plan-selection data and bounded correctness databases
#   5. Compare DuckDB/PGPlan/OuterYan for every selected corpus query
#
# Environment overrides (all optional):
#   GRAPH_DATASET    bitcoin (default) | epinions | google | wiki | dblp
#   TPCH_SF          TPC-H scale factor (default 100)
#   TPCDS_SF         TPC-DS scale factor (default 100)
#   OY_THREADS       Multi-thread profile/timing count (default 48)
#   OY_RUNS          Timed iterations per config (default 3, median taken)
#   JOBS             Make parallelism (default: nproc)
#   SKIP_BUILD       Set to 1 to skip compilation (use existing binary)
#   SKIP_DATA        Set to 1 to skip target DuckDB database generation
#   SKIP_QUERY_GEN   Set to 1 to keep the existing generated benchmark
#   RUN_PGPLAN       Set to 0 to use the legacy two-way harness (default 1)
#   PGPLAN_SETUP     source (default, auto-installs) | docker | external
#   SKIP_PG_DATA     Set to 1 to require existing exact TPC-H SF0.01 data
#   PGPLAN_CORPUS    PGPlan corpus root (default: outerjoin_query, 206 queries)
#   PGPLAN_SAMPLE_ROWS  Per-table graph/TPC-DS/JOB plan sample (default 1000)
#   PGPLAN_CORRECTNESS_GRAPH_ROWS  Small exact-check graph prefix (default 500)
#   PGPLAN_CORRECTNESS_JOB_ROWS  Small exact-check JOB prefix (default 1000)
#   PGPLAN_CORRECTNESS_MAX_RESULT_ROWS  Small-result preflight cap (default 2000000)
#   PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS  Small-DB preflight limit (default 30)
#   PGPLAN_CAPTURE_TIMEOUT_SECS  Plain PG EXPLAIN limit (default 60)
#   PGPLAN_TIMEOUT_SECS  DuckDB/per-postprocess step limit (default 1800)
#   OY_CORPUS        Custom corpus for RUN_PGPLAN=0 legacy two-way mode
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
. "$SCRIPT_DIR/configs.sh"

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
PGPLAN_RESULT_DIRS=()
RUN_PGPLAN="${RUN_PGPLAN:-${RUN_PG_REPLAY:-1}}"
CUSTOM_CORPUS="$CALLER_OY_CORPUS"

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
    python3 "$SCRIPT_DIR/gen_outerjoin_benchmark.py" 2>&1 | tee -a "$RUN_LOG"
else
    log "Step 3/5: Skipping benchmark generation (SKIP_QUERY_GEN=1)"
fi

# --- Step 4/5: PostgreSQL-backed three-way corpus ---------------------------
run_pgplan_corpus() {
    local corpus out_dir
    corpus="${PGPLAN_CORPUS:-${CUSTOM_CORPUS:-$SCRIPT_DIR/outerjoin_query}}"
    out_dir="${PGPLAN_OUT:-$SCRIPT_DIR/results/pgplan_corpus_${RUN_TS}}"
    [ -x "$SCRIPT_DIR/pgplan/corpus_experiment.sh" ] || \
        err "PGPlan corpus helper not found: $SCRIPT_DIR/pgplan/corpus_experiment.sh"

    log "Step 4/5: Preparing PostgreSQL 16.2 plan data and bounded correctness databases"
    log "Step 5/5: Comparing DuckDB, PGPlan, and OuterYan across $corpus"
    bash "$SCRIPT_DIR/pgplan/corpus_experiment.sh" \
        --corpus "$corpus" \
        --duckdb-bin "$DUCKDB_BIN" \
        --pg-dsn "$PG_DSN" \
        --rows "${PGPLAN_SAMPLE_ROWS:-1000}" \
        --threads "${PGPLAN_THREADS:-${OY_THREADS:-1}}" \
        --out "$out_dir" \
        "${EXPERIMENT_ARGS[@]}" \
        2>&1 | tee -a "$RUN_LOG"
    PGPLAN_RESULT_DIRS+=("$out_dir")
}

# --- Step 5: Run corpus experiments -----------------------------------------
run_experiment() {
    local label="$1" corpus="$2" default_only="$3" out
    out="$SCRIPT_DIR/results/experiment_onoff_${label}_${RUN_TS}.txt"
    log "Step 5/5: Running $label on/off experiment"
    OY_CORPUS="$corpus" bash "$SCRIPT_DIR/experiment_onoff.sh" \
        --only "$default_only" "${EXPERIMENT_ARGS[@]}" -o "$out" \
        2>&1 | tee -a "$RUN_LOG"
    RESULT_TXTS+=("$out")
}

STEP4_START=$SECONDS
if [ "$RUN_PGPLAN" = "1" ]; then
    run_pgplan_corpus
elif [ -n "$CUSTOM_CORPUS" ]; then
    log "Step 4/5: PGPlan disabled (RUN_PGPLAN=0)"
    run_experiment "custom" "$CUSTOM_CORPUS" "all"
else
    log "Step 4/5: PGPlan disabled (RUN_PGPLAN=0)"
    run_experiment "benchmark" "$SCRIPT_DIR/outerjoin_query" "all"
fi
log "Experiments complete ($(elapsed $((SECONDS - STEP4_START))))"

# --- Summary -----------------------------------------------------------------
TOTAL=$((SECONDS - START_TIME))
log "All done! Total time: $(elapsed $TOTAL)"
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
            echo "Three-way result directory: $result_dir"
            echo "Three-way status summary: $result_dir/status.tsv"
            echo "Three-way plan artifacts: $result_dir/artifacts"
        done
    fi
fi
