#!/usr/bin/env bash
# ============================================================================
# run_all.sh — Build + data + experiment + statistics/figures (Linux server)
#
# Assumes the repo is already cloned. Run from the repo root:
#   bash auto_test/run_all.sh [--query-type all|join|graph|aggregate]
#
# What it does:
#   1. Compile DuckDB release with required extensions (tpch, tpcds)
#   2. Build the databases required by the selected benchmark strata
#   3. Use committed queries; regenerate/verify only with --generate-queries
#   4. Run the Original/OuterYan bare-query comparison for the corpus
#   5. Publish statistics and figures (no LaTeX)
#
# Environment overrides (all optional):
#   GRAPH_DATASET    bitcoin (default) | epinions | google | wiki | dblp
#   TPCH_SF          TPC-H scale factor (default 50)
#   TPCDS_SF         TPC-DS scale factor (default 50)
#   TPCH_DB/TPCDS_DB Explicit paths (defaults: tpch_<SF>.duckdb / tpcds_<SF>.duckdb)
#   OY_THREAD_COUNTS Sequential timing counts (default "32")
#   OY_THREADS       Override with one multi-thread timing count
#   OY_PROFILE       One pre-timing profile per side (default 1; set 0 to skip)
#   --threads LIST   CLI override, e.g. "16 32" or 16,32
#   OY_RUNS          Timed iterations after warm-up/profiling (default 5; median)
#   --runs N         Override OY_RUNS with a positive odd sample count
#   OY_CHECK_CORRECTNESS  Compare every query's result multisets (default 0 here)
#   OY_TIMEOUT_SECS  Shared default per statement (600 seconds; 10 minutes)
#   OY_DUCKDB_TIMEOUT_SECS / OY_OUTERYAN_TIMEOUT_SECS  Independent engine limits
#   --timeout S      Set both limits; 0 disables the timeout
#   --duckdb-timeout S / --outeryan-timeout S  Per-engine overrides
#   JOBS             Make parallelism (default: nproc)
#   PYTHON_BIN       Python 3.10+ interpreter (default: python3; may be repo-local)
#   SKIP_BUILD       Set to 1 to skip compilation (use existing binary)
#   SKIP_DATA        Set to 1 to skip target DuckDB database generation
#   --generate-queries  Explicitly regenerate and byte-verify the frozen workload
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
export OY_CHECK_CORRECTNESS="${OY_CHECK_CORRECTNESS:-0}"
. "$SCRIPT_DIR/configs.sh"
. "$SCRIPT_DIR/thread_sweep.sh"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHON_BIN

cd "$REPO_ROOT"

RUN_TS="$(date '+%Y%m%d_%H%M%S')"
RUN_LOG="$SCRIPT_DIR/results/run_all_${RUN_TS}.log"

# --- Helpers -----------------------------------------------------------------
log() { printf '\n\033[1;36m===> %s\033[0m\n' "$*"; }
err() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
elapsed() { local s=$1; printf '%dm%02ds' $((s/60)) $((s%60)); }
usage() {
    printf '%s\n' \
        'Usage: bash auto_test/run_all.sh [OPTIONS] [experiment_onoff.sh options]' \
        'Default: build release, reuse/build data, test committed queries, publish statistics + PDF/PNG.' \
        '  --generate-queries     Regenerate the frozen SQL/manifests and verify byte identity before testing' \
        '  --prepare-only         Generate and verify only; no build, data downloads, or query execution' \
        '  --report-only          Reprocess results only; no build, generation, downloads, or query execution' \
        '  --csv PATH             Complete result CSV for --report-only (repeat for disjoint inputs)' \
        '  --date YYYYMMDD        Report date directory (default: today)' \
        '  --output-dir DIR       Explicit report directory override' \
        '  --skip-build           Reuse the release binary' \
        '  --skip-data            Reuse databases without preparing data' \
        '  --no-figures           Statistics only; no PDF/PNG' \
        '  --dry-run              Show stages without creating files or running queries' \
        '  --threads N[,N...]     Thread counts, sequentially (default: 32)' \
        '  --runs N               Positive odd timing sample count (default: 5, median)' \
        '  --timeout 600          Independent per-statement, per-engine limit; not a combined sample budget' \
        '  --check-correctness    Enable full bare-query result comparison (off by default here)' \
        'No LaTeX is generated. Report-only without --csv replays pinned local history, if present.' \
        'Subset/custom runs retain harness statistics; full-cohort plots require the complete active manifest.'
}

if [[ "$PYTHON_BIN" == */* ]]; then
    [ -x "$PYTHON_BIN" ] || err "Python binary is not executable: $PYTHON_BIN"
else
    command -v "$PYTHON_BIN" >/dev/null 2>&1 || err "Python binary was not found: $PYTHON_BIN"
fi
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || \
    err "Python 3.10 or newer is required: $PYTHON_BIN"

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
GENERATE_QUERIES=0
PREPARE_ONLY=0
REPORT_ONLY=0
NO_FIGURES=0
DRY_RUN=0
FULL_COHORT=1
REPORT_DATE="${RUN_TS:0:8}"
OUTPUT_DIR=""
REPORT_INPUTS=()
REPORT_DIRS=()
[ -z "$CUSTOM_CORPUS" ] || FULL_COHORT=0

# The built-in corpus is already deduplicated; selection is by query type.
argument_index=0
while [ "$argument_index" -lt "${#RAW_EXPERIMENT_ARGS[@]}" ]; do
    argument="${RAW_EXPERIMENT_ARGS[$argument_index]}"
    case "$argument" in
        -h|--help) usage; exit 0;;
        --generate-queries) GENERATE_QUERIES=1; argument_index=$((argument_index + 1));;
        --prepare-only) PREPARE_ONLY=1; GENERATE_QUERIES=1; argument_index=$((argument_index + 1));;
        --report-only) REPORT_ONLY=1; argument_index=$((argument_index + 1));;
        --no-figures) NO_FIGURES=1; argument_index=$((argument_index + 1));;
        --dry-run) DRY_RUN=1; argument_index=$((argument_index + 1));;
        --skip-build) export SKIP_BUILD=1; argument_index=$((argument_index + 1));;
        --skip-data) export SKIP_DATA=1; argument_index=$((argument_index + 1));;
        --date|--output-dir|--csv)
            [ "$((argument_index + 1))" -lt "${#RAW_EXPERIMENT_ARGS[@]}" ] || err "$argument requires a value"
            value="${RAW_EXPERIMENT_ARGS[$((argument_index + 1))]}"
            case "$argument" in
                --date) REPORT_DATE="$value";;
                --output-dir) OUTPUT_DIR="$value";;
                --csv) REPORT_INPUTS+=(--csv "$value");;
            esac
            argument_index=$((argument_index + 2));;
        --version|--corpus-version)
            err "Version selection is retired; use --query-type join, graph, or aggregate";;
        --threads)
            [ "$((argument_index + 1))" -lt "${#RAW_EXPERIMENT_ARGS[@]}" ] || err "--threads requires a value"
            THREAD_COUNTS="${RAW_EXPERIMENT_ARGS[$((argument_index + 1))]}"
            EXPERIMENT_ARGS+=("$argument" "$THREAD_COUNTS")
            argument_index=$((argument_index + 2));;
        --only|--query-type|--query-list|--limit|--pattern|--exclude|--corpus-scope)
            [ "$((argument_index + 1))" -lt "${#RAW_EXPERIMENT_ARGS[@]}" ] || err "$argument requires a value"
            value="${RAW_EXPERIMENT_ARGS[$((argument_index + 1))]}"
            if [[ "$argument" != --only && "$argument" != --query-type ]] || [ "$value" != all ]; then
                FULL_COHORT=0
            fi
            EXPERIMENT_ARGS+=("$argument" "$value")
            argument_index=$((argument_index + 2));;
        *)
            EXPERIMENT_ARGS+=("$argument")
            argument_index=$((argument_index + 1));;
    esac
done
oy_parse_thread_counts "$THREAD_COUNTS" || exit $?
[[ "$REPORT_DATE" =~ ^[0-9]{8}$ ]] || err "--date must be YYYYMMDD"
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/results/plots/$REPORT_DATE}"
[ "$REPORT_ONLY" -eq 0 ] || [ "$GENERATE_QUERIES" -eq 0 ] || err "--report-only cannot regenerate queries"
[ "${#REPORT_INPUTS[@]}" -eq 0 ] || [ "$REPORT_ONLY" -eq 1 ] || err "--csv requires --report-only"
[ "$GENERATE_QUERIES" -eq 0 ] || [ -z "$CUSTOM_CORPUS" ] || err "Cannot regenerate a custom OY_CORPUS"
[ "$GENERATE_QUERIES" -eq 0 ] || [ "${SKIP_QUERY_GEN:-0}" != 1 ] || err "--generate-queries conflicts with SKIP_QUERY_GEN=1"
PUBLISH_ARGS=(--output-dir "$OUTPUT_DIR")
[ "$NO_FIGURES" -eq 0 ] || PUBLISH_ARGS+=(--no-figures)

if [ "$DRY_RUN" -eq 1 ]; then
    if [ "$REPORT_ONLY" -eq 1 ]; then
        printf '%q ' "$PYTHON_BIN" "$SCRIPT_DIR/publish_plan_cohort.py" "${PUBLISH_ARGS[@]}"
        if [ "${#REPORT_INPUTS[@]}" -gt 0 ]; then printf '%q ' "${REPORT_INPUTS[@]}"; fi
        printf '\n'
    else
        if [ "$GENERATE_QUERIES" -eq 1 ]; then
            printf '%q ' "$PYTHON_BIN" "$SCRIPT_DIR/gen_outerjoin_benchmark.py"; printf '\n'
            printf '%q ' "$PYTHON_BIN" "$SCRIPT_DIR/verify_benchmark_reproduction.py"; printf '\n'
        else
            echo 'Use existing committed queries (no generation).'
        fi
        if [ "$PREPARE_ONLY" -eq 0 ]; then
            echo "Build release: $([ "${SKIP_BUILD:-0}" = 1 ] && echo skip || echo yes); prepare data: $([ "${SKIP_DATA:-0}" = 1 ] && echo skip || echo yes)"
            printf '%q ' bash "$SCRIPT_DIR/experiment_onoff.sh" "${EXPERIMENT_ARGS[@]}"; printf '\n'
            echo "Sequential thread counts: $THREAD_COUNTS"
            echo "Statistics/figures: $OUTPUT_DIR (only this run's CSV; no LaTeX). Full-cohort publication=$FULL_COHORT"
        fi
    fi
    exit 0
fi

if [ "$PREPARE_ONLY" -eq 0 ] && { [ "$FULL_COHORT" -eq 1 ] || [ "$REPORT_ONLY" -eq 1 ]; }; then
    "$PYTHON_BIN" -c 'import numpy, pandas' || err "Install auto_test/report_requirements.txt before starting"
    if [ "$NO_FIGURES" -eq 0 ]; then
        "$PYTHON_BIN" -c 'import inspect; from matplotlib.axes import Axes; assert "orientation" in inspect.signature(Axes.violinplot).parameters' || \
            err "Install auto_test/report_requirements.txt before starting (Matplotlib 3.10+ required)"
    fi
fi
if [ "$REPORT_ONLY" -eq 1 ]; then
    if [ "${#REPORT_INPUTS[@]}" -gt 0 ]; then
        exec "$PYTHON_BIN" "$SCRIPT_DIR/publish_plan_cohort.py" "${PUBLISH_ARGS[@]}" "${REPORT_INPUTS[@]}"
    else
        exec "$PYTHON_BIN" "$SCRIPT_DIR/publish_plan_cohort.py" "${PUBLISH_ARGS[@]}"
    fi
fi
[ "${FORCE:-0}" != 1 ] || err "Unset FORCE: the complete workflow reuses existing databases and must not delete them"
mkdir -p "$SCRIPT_DIR/results"

# Regeneration is opt-in, before compilation or data downloads. Default validation
# only reads the committed inputs; it does not invoke the generator/codegen.
if [ "$GENERATE_QUERIES" -eq 1 ]; then
    log "Regenerating benchmark SQL and provenance manifests"
    "$PYTHON_BIN" "$SCRIPT_DIR/gen_outerjoin_benchmark.py" 2>&1 | tee -a "$RUN_LOG"
    "$PYTHON_BIN" "$SCRIPT_DIR/verify_benchmark_reproduction.py" \
        --output "$OUTPUT_DIR/query_reproduction.json" 2>&1 | tee -a "$RUN_LOG"
elif [ "$FULL_COHORT" -eq 1 ]; then
    "$PYTHON_BIN" "$SCRIPT_DIR/verify_benchmark_reproduction.py" --validate-only 2>&1 | tee -a "$RUN_LOG"
fi
[ "$PREPARE_ONLY" -eq 0 ] || exit 0

# Full runs use the current policy reporter below. The bare/subset harness retains
# its existing legacy complete-pair summary, clearly separate from cohort reports.
if [ "$FULL_COHORT" -eq 1 ]; then
    export OY_DEFER_STATISTICS=1
fi

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

log "Step 3/4: Using the validated active queries (regeneration requested=$GENERATE_QUERIES)"

# --- Step 4: Run corpus experiments -----------------------------------------
run_experiment() {
    local label="$1" corpus="$2" default_only="$3" out experiment_status=0
    out="$SCRIPT_DIR/results/experiment_onoff_${label}_${RUN_TS}_t${OY_THREADS}.txt"
    [ ! -e "$out" ] && [ ! -e "${out%.txt}.csv" ] || err "Result path already exists: $out; refusing to overwrite a previous run"
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
    if [ "$FULL_COHORT" -eq 1 ]; then
        report_dir="$OUTPUT_DIR"
        if [ "${#OY_THREAD_VALUES[@]}" -gt 1 ]; then
            report_dir="$OUTPUT_DIR/t$thread_count"
        fi
        result_txt="${RESULT_TXTS[$((${#RESULT_TXTS[@]} - 1))]}"
        publish_args=(--csv "${result_txt%.txt}.csv" --output-dir "$report_dir")
        [ "$NO_FIGURES" -eq 0 ] || publish_args+=(--no-figures)
        log "Publishing this run's statistics and figures (no LaTeX)"
        if "$PYTHON_BIN" "$SCRIPT_DIR/publish_plan_cohort.py" "${publish_args[@]}" 2>&1 | tee -a "$RUN_LOG"; then
            REPORT_DIRS+=("$report_dir")
        else
            publish_status=$?
            [ "$RUN_STATUS" -ne 0 ] || RUN_STATUS="$publish_status"
            echo "Publication failed for ${result_txt%.txt}.csv; no historical results substituted." >&2
        fi
    fi
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
        if [ "$FULL_COHORT" -eq 0 ]; then
            echo "Subset statistics (legacy complete-pair policy): ${result_txt%.txt}_statistics/"
        fi
        if [ -d "${result_txt%.txt}.plans" ]; then
            echo "Plan artifacts: ${result_txt%.txt}.plans"
        fi
    done
fi
if [ "${#REPORT_DIRS[@]}" -gt 0 ]; then
    for report_dir in "${REPORT_DIRS[@]}"; do
        echo "Statistics and figures: $report_dir"
    done
fi
# Preserve the corpus helper's failure status, but only after handing all
# generated status, timing, and failure-report paths back to the caller.
if [ "$RUN_STATUS" -ne 0 ]; then
    exit "$RUN_STATUS"
fi
