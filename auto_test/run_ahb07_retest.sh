#!/usr/bin/env bash
# A-H-B-07 only: one original control and six date-window candidates.
set -euo pipefail
if [[ "$#" != 1 || "$1" != --run ]]; then
    echo 'Usage: bash auto_test/run_ahb07_retest.sh --run'
    exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
export DUCKDB_BIN="$REPO_ROOT/build/release/duckdb"
export TPCH_SF=50 TPCH_DB="$REPO_ROOT/tpch_50.duckdb"
export PYTHON_BIN="${PYTHON_BIN:-python3}"
[[ -x "$DUCKDB_BIN" && -f "$TPCH_DB" ]] || { echo 'Release binary and SF50 database required' >&2; exit 2; }
unset OY_CONFIG_LOADED OY_CORPUS_VERSION DUCKDB_OY_FORCE_CANDIDATE
unset DUCKDB_OY_SIMPLIFY_SCAN_FILTERS DUCKDB_OYTRACE DUCKDB_OY_PROFILE_TRACE DUCKDB_SJ_KERNEL_TRACE
export OY_REPO_ROOT="$REPO_ROOT" OY_CORPUS_SCOPE=benchmark FORCE=0
export OY_CHECK_CORRECTNESS=0 OY_PROFILE=1 OY_CAPTURE_PLANS=1
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
BASE="$SCRIPT_DIR/results/experiment_onoff_ahb07_windows_${RUN_TS}_t32"
export OY_CORPUS="${BASE}.corpus"
mkdir -p "$SCRIPT_DIR/results"
exec > >(tee "${BASE}.run.log") 2>&1
echo 'A-H-B-07: one original and six candidates; 32 threads; five timed samples (median)'
echo '600 seconds per execution per engine; warmup/profile separate; correctness disabled'
echo 'Existing Release binary; no optimizer, cost-model or active-query changes'
echo "COMMIT=$(git rev-parse HEAD)"
echo "RUN_LOG=${BASE}.run.log"
"$PYTHON_BIN" "$SCRIPT_DIR/prepare_ahb07_retest.py" --out "$OY_CORPUS" \
    --bin "$DUCKDB_BIN" --tpch-db "$TPCH_DB" --tpch-sf 50 --threads 32
bash "$SCRIPT_DIR/experiment_onoff.sh" --only tpch --query-list "$OY_CORPUS/queries.txt" \
    --threads 32 --runs 5 --timeout 600 --profile --no-check-correctness \
    --capture-plans --out "${BASE}.txt"
echo 'CPU9_AHB07_EXIT=0'
