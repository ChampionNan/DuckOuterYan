#!/usr/bin/env bash
# G-H-LD-05 only: original control and three isolated input-filter candidates.
set -euo pipefail
if [[ "$#" != 1 || "$1" != --run ]]; then
    echo 'Usage: bash auto_test/run_custdist_retest.sh --run'
    exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
export DUCKDB_BIN="$REPO_ROOT/build/release/duckdb"
export TPCH_SF=50 TPCH_DB="$REPO_ROOT/tpch_50.duckdb"
export PYTHON_BIN="${PYTHON_BIN:-python3}"
[[ -x "$DUCKDB_BIN" && -f "$TPCH_DB" ]] || {
    echo 'Existing Release binary and TPC-H SF50 database required' >&2; exit 2;
}
if pgrep -x duckdb >/dev/null; then
    echo 'Another DuckDB process is running; do not overlap performance tests' >&2
    exit 2
fi
# Prevent inherited force-candidate or experimental optimizer knobs.
while IFS= read -r variable; do
    case "$variable" in DUCKDB_OY*|DUCKDB_SJ_*) unset "$variable";; esac
done < <(compgen -e)
unset OY_CONFIG_LOADED OY_CORPUS_VERSION
export OY_REPO_ROOT="$REPO_ROOT" OY_CORPUS_SCOPE=benchmark FORCE=0
export OY_CHECK_CORRECTNESS=0 OY_PROFILE=1 OY_CAPTURE_PLANS=1
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
BASE="$SCRIPT_DIR/results/experiment_onoff_custdist_predicate_${RUN_TS}_t32"
export OY_CORPUS="$SCRIPT_DIR/outerjoin_benchmark/candidates/custdist_predicate_20261015"
mkdir -p "$SCRIPT_DIR/results"
exec > >(tee "${BASE}.run.log") 2>&1
echo 'G-H-LD-05: original control plus three input-filter candidates; no active benchmark changes'
echo 'SF50; normal cost gate; 32 threads; five timed executions (median)'
echo '600 seconds per execution per engine; warmup/profiles excluded; full SF50 correctness disabled'
echo 'Small-fixture bare-query correctness is checked before timing; no rebuild or optimizer changes'
echo "COMMIT=$(git rev-parse HEAD)"
echo "RUN_LOG=${BASE}.run.log"
echo "RESULT_CSV=${BASE}.csv"
"$PYTHON_BIN" "$SCRIPT_DIR/verify_custdist_retest.py" --corpus "$OY_CORPUS" \
    --bin "$DUCKDB_BIN" --db "$TPCH_DB" --sf 50 --threads 32 --out "${BASE}.validation.json"
"$PYTHON_BIN" - "${BASE}.validation.json" <<'PY'
import json
import sys

audit = json.load(open(sys.argv[1]))
expected_binary = 'ebed1e51e170d26ce2e577bdb56490686fff29c0bbeb54ef75f1bb06bb17aacf'
expected_database = '769a67198be2d4e0fe4dd0a71f70bf5ab15e42122c866e2280c64844fae4405b'
if audit['binary_sha256'] != expected_binary or audit['database_signature'] != expected_database:
    raise SystemExit('CPU9 Release binary/database differs from the approved baseline; review before timing')
for row in audit['candidates']:
    if row['placement'] == 'input' or row['days'] == 840:
        if row['decision']['selected_plan'] != 'OUTERYAN':
            raise SystemExit('Candidate is a fallback, not an OuterYan optimization: ' + row['query'])
print('CPU9 scale, binary, database and normal-gate selections verified', flush=True)
PY
bash "$SCRIPT_DIR/experiment_onoff.sh" --only all --query-list "$OY_CORPUS/timing_queries.txt" \
    --threads 32 --runs 5 --timeout 600 --profile --no-check-correctness \
    --capture-plans --out "${BASE}.txt"
echo 'CPU9_CUSTDIST_RETEST_EXIT=0'
