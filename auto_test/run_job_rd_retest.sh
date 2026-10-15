#!/usr/bin/env bash
# One unchanged JOB control and five year-window candidates; never promote.
set -euo pipefail
case "${1:---help}" in
    --run) ;;
    --help|-h) echo 'Usage: bash auto_test/run_job_rd_retest.sh --run'; exit 0 ;;
    *) echo 'Expected --run or --help' >&2; exit 2 ;;
esac
[ "$#" -le 1 ] || { echo 'Unexpected arguments' >&2; exit 2; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
# Do not overlap the existing full-run harness, even between query processes.
if pgrep -u "$(id -u)" -f '^bash ([^ ]*/)?(experiment_onoff|run_all)\.sh( |$)' >/dev/null \
        || pgrep -u "$(id -u)" -x duckdb >/dev/null; then
    echo 'An experiment or DuckDB process is running; wait for it to finish.' >&2
    exit 2
fi
export DUCKDB_BIN="$REPO_ROOT/build/release/duckdb"
export JOB_DB="${JOB_DB:-$REPO_ROOT/job_db}" PYTHON_BIN="${PYTHON_BIN:-python3}"
[ -x "$DUCKDB_BIN" ] && [ -f "$JOB_DB" ] || {
    echo 'Existing Release binary and JOB database required' >&2; exit 2;
}
unset OY_CONFIG_LOADED OY_CORPUS_VERSION DUCKDB_OY_FORCE_CANDIDATE
unset DUCKDB_OY_SIMPLIFY_SCAN_FILTERS DUCKDB_OYTRACE DUCKDB_OY_PROFILE_TRACE DUCKDB_SJ_KERNEL_TRACE
export OY_REPO_ROOT="$REPO_ROOT" OY_CORPUS_SCOPE=benchmark FORCE=0
export OY_CHECK_CORRECTNESS=0 OY_PROFILE=1 OY_CAPTURE_PLANS=1
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
BASE="$SCRIPT_DIR/results/experiment_onoff_job_rd_selectivity_${RUN_TS}_t32"
export OY_CORPUS="${BASE}.corpus"
mkdir -p "$SCRIPT_DIR/results"
exec > >(tee "${BASE}.run.log") 2>&1
echo 'JOB A-J-RD-01: one control + five predicate-only candidates; active benchmark unchanged'
echo '32 threads; 5 timed executions (median); each statement/engine timeout=600s'
echo 'Warm-up and profile excluded; correctness disabled for CPU9 performance run; cost gate enabled'
echo "COMMIT=$(git rev-parse HEAD)"
"$PYTHON_BIN" "$SCRIPT_DIR/prepare_job_rd_retest.py" --out "$OY_CORPUS" \
    --bin "$DUCKDB_BIN" --job-db "$JOB_DB" --threads 32
bash "$SCRIPT_DIR/experiment_onoff.sh" --only job --query-list "$OY_CORPUS/queries.txt" \
    --threads 32 --runs 5 --timeout 600 --profile --no-check-correctness \
    --capture-plans --out "${BASE}.txt"
echo 'CPU9_JOB_RD_EXIT=0'
