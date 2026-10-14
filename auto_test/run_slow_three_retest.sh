#!/usr/bin/env bash
# Three original controls and thirteen predicate-only alternatives. No promotion.
set -euo pipefail
case "${1:---help}" in
    --run) ;;
    --help|-h) echo 'Usage: bash auto_test/run_slow_three_retest.sh --run'; exit 0;;
    *) echo 'Expected --run or --help' >&2; exit 2;;
esac
[ "$#" -le 1 ] || { echo 'Unexpected arguments' >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
export DUCKDB_BIN="$REPO_ROOT/build/release/duckdb"
export TPCH_SF=50 TPCH_DB="$REPO_ROOT/tpch_50.duckdb" JOB_DB="$REPO_ROOT/job_db"
export PYTHON_BIN="${PYTHON_BIN:-python3}"
[ -x "$DUCKDB_BIN" ] && [ -f "$TPCH_DB" ] && [ -f "$JOB_DB" ] || {
    echo 'Existing Release binary, TPC-H SF50 and JOB databases required' >&2; exit 2;
}
unset OY_CONFIG_LOADED OY_CORPUS_VERSION DUCKDB_OY_FORCE_CANDIDATE
unset DUCKDB_OY_SIMPLIFY_SCAN_FILTERS DUCKDB_OYTRACE DUCKDB_OY_PROFILE_TRACE DUCKDB_SJ_KERNEL_TRACE
export OY_REPO_ROOT="$REPO_ROOT" OY_CORPUS_SCOPE=benchmark FORCE=0
export OY_CHECK_CORRECTNESS=0 OY_PROFILE=1 OY_CAPTURE_PLANS=1
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
BASE="$SCRIPT_DIR/results/experiment_onoff_slow_three_selectivity_${RUN_TS}_t32"
export OY_CORPUS="${BASE}.corpus"
mkdir -p "$SCRIPT_DIR/results"
exec > >(tee "${BASE}.run.log") 2>&1
echo 'Three controls + thirteen selectivity candidates; lower tiers explicitly labelled'
echo 'SF50; 32 threads; five timed executions (median); each execution/engine limited to 600 seconds'
echo 'Warmup and profiling excluded from timing; correctness disabled; no promotion or optimizer changes'
echo "COMMIT=$(git rev-parse HEAD)"
echo "RUN_LOG=${BASE}.run.log"
echo "RESULT_CSV=${BASE}.csv"
"$PYTHON_BIN" "$SCRIPT_DIR/prepare_slow_three_retest.py" --out "$OY_CORPUS" \
    --bin "$DUCKDB_BIN" --tpch-db "$TPCH_DB" --tpch-sf 50 --job-db "$JOB_DB" --threads 32
bash "$SCRIPT_DIR/experiment_onoff.sh" --only all --query-list "$OY_CORPUS/queries.txt" \
    --threads 32 --runs 5 --timeout 600 --profile --no-check-correctness \
    --capture-plans --out "${BASE}.txt"
echo 'CPU9_SLOW_THREE_EXIT=0'
