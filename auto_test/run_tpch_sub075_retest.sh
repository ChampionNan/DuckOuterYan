#!/usr/bin/env bash
# Initial WHERE pilots, or two input-filter follow-ups for A-H-RD-11. No promotion.
set -euo pipefail
if [[ "$#" != 1 || ( "$1" != --run && "$1" != --input-followup ) ]]; then
    echo 'Usage: bash auto_test/run_tpch_sub075_retest.sh --run|--input-followup'
    exit 2
fi
PILOT_MODE="$1"
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
while IFS= read -r variable; do
    case "$variable" in DUCKDB_OY*|DUCKDB_SJ_*) unset "$variable";; esac
done < <(compgen -e)
unset OY_CONFIG_LOADED OY_CORPUS_VERSION
export OY_REPO_ROOT="$REPO_ROOT" OY_CORPUS_SCOPE=benchmark FORCE=0
export OY_CHECK_CORRECTNESS=0 OY_PROFILE=1 OY_CAPTURE_PLANS=1
RUN_TS="$(date '+%Y%m%d_%H%M%S')"
RUN_NAME=tpch_sub075
[[ "$PILOT_MODE" != --input-followup ]] || RUN_NAME=tpch_sub075_input_followup
BASE="$SCRIPT_DIR/results/experiment_onoff_${RUN_NAME}_${RUN_TS}_t32"
export OY_CORPUS="$SCRIPT_DIR/outerjoin_benchmark/candidates/tpch_sub075_20261015"
mkdir -p "$SCRIPT_DIR/results"
exec > >(tee "${BASE}.run.log") 2>&1
if [[ "$PILOT_MODE" == --input-followup ]]; then
    echo 'A-H-RD-11: input_d480 and input_d240 follow-ups after the WHERE-only pilot'
else
    echo 'Q-H-LD-36, A-H-RD-10, A-H-RD-11: original controls and predicate candidates'
fi
echo 'SF50; normal cost gate; 32 threads; five timed executions (median)'
echo '600 seconds per execution per engine; warmup/profiles separate; no full SF50 correctness timing'
echo 'Tiny-fixture correctness before timing; no active benchmark, optimizer or binary changes'
echo "COMMIT=$(git rev-parse HEAD)"
echo "RUN_LOG=${BASE}.run.log"
echo "RESULT_CSV=${BASE}.csv"
"$PYTHON_BIN" "$SCRIPT_DIR/prepare_tpch_sub075_retest.py" --corpus "$OY_CORPUS" \
    --bin "$DUCKDB_BIN" --db "$TPCH_DB" --sf 50 --threads 32 --audit "${BASE}.validation.json"
"$PYTHON_BIN" - "${BASE}.validation.json" "$OY_CORPUS/manifest.csv" "${BASE}.queries.txt" "$PILOT_MODE" <<'PY'
import csv
import json
import sys

with open(sys.argv[1]) as handle:
    audit = json.load(handle)
if audit['binary_sha256'] != 'ebed1e51e170d26ce2e577bdb56490686fff29c0bbeb54ef75f1bb06bb17aacf':
    raise SystemExit('CPU9 binary differs from baseline; review before timing')
if audit['database_signature'] != '769a67198be2d4e0fe4dd0a71f70bf5ab15e42122c866e2280c64844fae4405b':
    raise SystemExit('CPU9 database differs from baseline; review before timing')
with open(sys.argv[2]) as handle:
    rows = {r['query_id']: r for r in csv.DictReader(handle)}
if len(audit['candidates']) != 21 or set(rows) != {r['query'] for r in audit['candidates']}:
    raise SystemExit('Expected exactly twenty-one verified definitions')
if sys.argv[4] == '--input-followup':
    shortlist = [r for r in audit['candidates'] if r['short_query'] == 'A-H-RD-11'
                 and r['variant'] in ('input_d480', 'input_d240')]
    expected, required_queries = 2, ('A-H-RD-11',)
else:
    shortlist = [r for r in audit['candidates'] if rows[r['query']]['pilot_run_group'] == 'sf50_shortlist']
    expected, required_queries = 12, ('Q-H-LD-36', 'A-H-RD-10', 'A-H-RD-11')
if len(shortlist) != expected:
    raise SystemExit('Unexpected number of SF50 trials')
selected = [r for r in shortlist if r['decision']['selected_plan'] == 'OUTERYAN']
for short in required_queries:
    if not any(r['short_query'] == short and r['variant'] != 'original' for r in selected):
        raise SystemExit('No normally selected candidate for ' + short)
with open(sys.argv[3], 'w') as handle:
    handle.write(''.join(rows[r['query']]['path'] + '\n' for r in selected))
for row in shortlist:
    if row not in selected:
        print('Not timed: fallback candidate ' + row['query'], flush=True)
print('Verified CPU9 binary/database/SQL; {} selected trials eligible'.format(len(selected)), flush=True)
PY
bash "$SCRIPT_DIR/experiment_onoff.sh" --only all --query-list "${BASE}.queries.txt" \
    --threads 32 --runs 5 --timeout 600 --profile --no-check-correctness \
    --capture-plans --out "${BASE}.txt"
echo 'CPU9_TPCH_SUB075_EXIT=0'
