#!/usr/bin/env bash
# Use the canonical checkout and existing databases; capture, validate, measure.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
build_dir=""
job_db=""
tpch_db=""
pg_bin=""
pgdata=""
out=""
jobs=4
runs=5
seeds=()
case_options=()
while (($#)); do
    case "$1" in
        --build-dir) build_dir="$2"; shift 2 ;;
        --job-db) job_db="$2"; shift 2 ;;
        --tpch-db) tpch_db="$2"; shift 2 ;;
        --tpcds-db) case_options+=(--tpcds-db "$2"); shift 2 ;;
        --specs) case_options+=(--specs "$2"); shift 2 ;;
        --pg-bin-dir) pg_bin="$2"; shift 2 ;;
        --pgdata) pgdata="$2"; shift 2 ;;
        --seed-capture) seeds+=(--seed-capture "$2"); shift 2 ;;
        --out) out="$2"; shift 2 ;;
        --jobs) jobs="$2"; shift 2 ;;
        --runs) runs="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
: "${build_dir:?--build-dir is required}"
: "${job_db:?--job-db is required}"
: "${tpch_db:?--tpch-db is required}"
: "${pg_bin:?--pg-bin-dir is required}"
: "${pgdata:?--pgdata is required}"
: "${out:?--out is required}"
((${#seeds[@]})) || { echo '--seed-capture is required' >&2; exit 2; }
[[ ! -e "$out" ]] || { echo 'Output directory already exists' >&2; exit 2; }
python="${PYTHON:-python3}"
"$python" - "$repo" "$build_dir" <<'PY'
from pathlib import Path
import sys
repo, build = map(Path, sys.argv[1:])
values = dict(line.split('=', 1) for line in (build / 'CMakeCache.txt').read_text().splitlines()
              if '=' in line and not line.startswith(('#', '//')))
if Path(values['CMAKE_HOME_DIRECTORY:INTERNAL']).resolve() != repo.resolve():
    raise SystemExit('build directory does not belong to this canonical checkout')
if values.get('CMAKE_BUILD_TYPE:STRING', '').lower() != 'release':
    raise SystemExit('performance measurements require a Release build')
PY
# Ninja's "duckdb" name resolves to the CLI output; explicitly build the
# shared library too, since the experiment client links against it.
if [[ -f "$build_dir/src/libduckdb.so" ]]; then
    shared_target=libduckdb.so
else
    shared_target=libduckdb.dylib
fi
cmake --build "$build_dir" --target duckdb "$shared_target" -j "$jobs"
mkdir -p "$out/bin"
out="$(cd "$out" && pwd)"
build_dir="$(cd "$build_dir" && pwd)"
pg_bin="$(cd "$pg_bin" && pwd)"
libdir="$build_dir/src"
pg_prefix="$(cd "$pg_bin/.." && pwd)"
"${CXX:-c++}" -std=c++17 -O2 -I"$repo/src/include" "$here/fair_replay_runner.cpp" \
    -L"$libdir" -lduckdb -Wl,-rpath,"$libdir" -o "$out/bin/fair_replay_runner"
"${CC:-cc}" -std=c11 -O2 -I"$pg_prefix/include" "$here/pg_bare_query.c" \
    -L"$pg_prefix/lib" -lpq -Wl,-rpath,"$pg_prefix/lib" -o "$out/bin/pg_bare_query"
if [[ -f "$libdir/libduckdb.so" ]]; then
    duckdb_lib="$libdir/libduckdb.so"
else
    duckdb_lib="$libdir/libduckdb.dylib"
fi
"$python" "$here/benchmark_pg.py" --repo "$repo" --duckdb "$build_dir/duckdb" \
    --job-db "$job_db" --tpch-db "$tpch_db" --pg-bin-dir "$pg_bin" --pgdata "$pgdata" \
    "${seeds[@]}" ${case_options[@]+"${case_options[@]}"} --out "$out/capture"
"$python" "$here/measure_benchmark_pg.py" --runner "$out/bin/fair_replay_runner" \
    --duckdb-lib "$duckdb_lib" --job-db "$job_db" --tpch-db "$tpch_db" \
    --capture "$out/capture" --pg-bin-dir "$pg_bin" --pg-stream "$out/bin/pg_bare_query" \
    --pgdata "$pgdata" ${case_options[@]+"${case_options[@]}"} --out "$out/verified" --runs "$runs"
