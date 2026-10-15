#!/usr/bin/env bash
# Always build the current checkout; keep the existing PG installation and results.
set -euo pipefail
source_dir="${OY_REPO_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)}"
study_dir="${PG_STUDY_DIR:-$source_dir/auto_test/results/pg-plan-study}"
export LC_ALL=C
export PATH="$study_dir/bin:$PATH"
cd "$source_dir"

pg_source=()
if [[ -f "$study_dir/work/postgresql-16.2.tar.gz" ]]; then
  pg_source=(--pg-source "$study_dir/work/postgresql-16.2.tar.gz")
fi

exec bash auto_test/pg_plan_comparison/server.sh all \
  --work-dir "$study_dir/work" --jobs 4 \
  --duckdb-build-dir "$source_dir/build/pg-plan-comparison-release" \
  "${pg_source[@]}" \
  --job-db "$source_dir/job_db" \
  --tpch-db "$source_dir/tpch_db" \
  --timeout 3600 --load-timeout 14400 \
  --out "$study_dir/results/run-$(date -u +%Y%m%dT%H%M%SZ)-$$" "$@"
