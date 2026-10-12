#!/usr/bin/env bash
# Full isolated TPC-H pilot: 31 reviewed candidates + 145 unchanged queries.
# Does not regenerate/promote the benchmark, rebuild DuckDB, or build databases.
set -euo pipefail
case "${1:---help}" in
    --run) ;;
    --help|-h) echo 'Usage: bash auto_test/run_tpch_tuning_retest.sh --run'; exit 0;;
    *) echo 'Expected --run or --help' >&2; exit 2;;
esac
[ "$#" -le 1 ] || { echo 'Unexpected arguments' >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
export DUCKDB_BIN="$REPO_ROOT/build/release/duckdb"
export TPCH_SF=50 TPCH_DB="$REPO_ROOT/tpch_50.duckdb"
export PYTHON_BIN="${PYTHON_BIN:-python3}"
[ -x "$DUCKDB_BIN" ] || { echo 'Release binary is required' >&2; exit 2; }
[ -f "$TPCH_DB" ] || { echo 'Existing tpch_50.duckdb is required' >&2; exit 2; }
unset OY_CONFIG_LOADED OY_CORPUS_VERSION
export OY_REPO_ROOT="$REPO_ROOT" OY_CORPUS_SCOPE=benchmark
export FORCE=0 OY_CHECK_CORRECTNESS=0 OY_PROFILE=1 OY_CAPTURE_PLANS=1
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
BASE="$SCRIPT_DIR/results/experiment_onoff_tpch_tuning_full_${RUN_TS}_t32"
export OY_CORPUS="${BASE}.corpus"
mkdir -p "$SCRIPT_DIR/results"
exec > >(tee "${BASE}.run.log") 2>&1
echo "TPC-H full pilot: 176 queries; SF50; 32 threads; 5 timed samples (median)"
echo "Timeout: 600 seconds for EACH execution on EACH engine"
echo "Correctness disabled for this performance run; profiles/plans enabled"
echo "COMMIT=$(git rev-parse HEAD)"
echo "RUN_LOG=${BASE}.run.log"
echo "RESULT_TXT=${BASE}.txt"
echo "RESULT_CSV=${BASE}.csv"
echo "PILOT_CORPUS=$OY_CORPUS"
"$DUCKDB_BIN" --version
"$PYTHON_BIN" "$SCRIPT_DIR/prepare_tpch_tuning_retest.py" \
    --out "$OY_CORPUS" --bin "$DUCKDB_BIN" --db "$TPCH_DB"
bash "$SCRIPT_DIR/experiment_onoff.sh" --only all --query-list "$OY_CORPUS/queries.txt" \
    --threads 32 --runs 5 --timeout 600 --profile --no-check-correctness \
    --capture-plans --out "${BASE}.txt"
echo 'CPU9_TPCH_FULL_EXIT=0'
