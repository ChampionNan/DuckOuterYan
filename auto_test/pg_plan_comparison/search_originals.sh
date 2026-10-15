#!/usr/bin/env bash
# Linux entry point. Uses the current checkout and existing read-only databases.
set -euo pipefail
search_repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
search_build=${1:-"$search_repo/build/pg-plan-comparison-release"}
search_out=${2:?Usage: search_originals.sh BUILD_DIRECTORY NEW_OUTPUT_DIRECTORY}
search_python=${PYTHON:-python3}
search_cxx=${CXX:-c++}
search_jobs=${JOBS:-4}
search_scripts="$search_repo/auto_test/pg_plan_comparison"

"$search_python" - "$search_repo" "$search_build" "$search_out" <<'PY'
from pathlib import Path
import sys
repo, build, out = map(lambda value: Path(value).resolve(), sys.argv[1:])
cache = dict(line.split('=', 1) for line in (build / 'CMakeCache.txt').read_text().splitlines()
             if '=' in line and not line.startswith(('#', '//')))
if Path(cache['CMAKE_HOME_DIRECTORY:INTERNAL']).resolve() != repo:
    raise SystemExit('Build directory belongs to a different source checkout')
if cache.get('CMAKE_BUILD_TYPE:STRING') != 'Release':
    raise SystemExit('A configured Release build is required')
for name in ('job_db', 'tpch_db', 'tpcds_db'):
    if not (repo / name).is_file():
        raise SystemExit('Missing existing database: ' + str(repo / name))
out.mkdir(parents=True, exist_ok=False)
PY

# Build both library and CLI: rebuilding only duckdb can leave the shell stale.
cmake --build "$search_build" --target duckdb shell -j "$search_jobs" >"$search_out/build.log" 2>&1
"$search_cxx" -std=c++17 -O2 -I"$search_repo/src/include" \
  "$search_scripts/bare_query_runner.cpp" -L"$search_build/src" -lduckdb \
  "-Wl,-rpath,$search_build/src" -o "$search_out/bare_query_runner"

"$search_python" "$search_scripts/inspect_original.py" --repo "$search_repo" \
  --duckdb "$search_build/duckdb" --out "$search_out/screen" --all --strip-outer-order-limit

mapfile -t search_queries < <("$search_python" - "$search_out/screen/summary.json" <<'PY'
import json, sys
for name, row in json.load(open(sys.argv[1])).items():
    if row.get('decision', {}).get('outer_reordered') == '1' and row['mode_status'].get('OuterYan') == 'ok':
        print(name)
PY
)
if ((${#search_queries[@]})); then
  "$search_python" "$search_scripts/diagnose_candidates.py" --repo "$search_repo" \
    --duckdb "$search_build/duckdb" --runner "$search_out/bare_query_runner" \
    --out "$search_out/candidates" --queries "${search_queries[@]}"
fi

mapfile -t search_variants < <("$search_python" - "$search_scripts/predicate_variants.json" <<'PY'
import json, sys
print('\n'.join(json.load(open(sys.argv[1]))))
PY
)
"$search_python" "$search_scripts/diagnose_candidates.py" --repo "$search_repo" \
  --duckdb "$search_build/duckdb" --runner "$search_out/bare_query_runner" \
  --out "$search_out/predicate-candidates" --variants "$search_scripts/predicate_variants.json" \
  --queries "${search_variants[@]}"

for search_batch in candidates predicate-candidates; do
  if [[ ! -f "$search_out/$search_batch/summary.json" ]]; then continue; fi
  mapfile -t search_valid < <("$search_python" - "$search_out/$search_batch/summary.json" <<'PY'
import json, sys
for name, row in json.load(open(sys.argv[1])).items():
    if row.get('status') == 'exact_match' and row['modes']['OFF']['run']['rows']:
        print(name)
PY
  )
  if ((${#search_valid[@]})); then
    "$search_python" "$search_scripts/measure_candidates.py" --repo "$search_repo" \
      --runner "$search_out/bare_query_runner" --validated "$search_out/$search_batch" \
      --out "$search_out/$search_batch-timing" --queries "${search_valid[@]}" --repeats 5
  fi
done
