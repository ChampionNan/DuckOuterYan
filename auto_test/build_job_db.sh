#!/usr/bin/env bash
# ============================================================================
# build_job_db.sh — Populate the JOB IMDb DuckDB database for DuckYanOuter.
#
# Two phases:
#   1. Download 21 official DuckDB IMDb parquet files (~1.75 GB total) from
#      the duckdb/duckdb-data v1.0 GitHub release into $JOB_PARQUET_DIR.
#   2. Run auto_test/build_job_db.sql with that directory bound to the
#      duckdb variable 'job_dir', which CREATE-OR-REPLACE-loads 21 tables
#      into $JOB_DB.
#
# Once $JOB_DB exists, --only job / bench / all run with no further network.
#
# Env overrides (all optional):
#   DUCKDB_BIN        Path to the DuckYanOuter duckdb binary (auto from
#                     test_config.sh).
#   JOB_DB            Output database file (default $REPO_ROOT/job_db).
#   JOB_PARQUET_DIR   Where to cache parquet files (default
#                     $REPO_ROOT/job_parquet).
#   FORCE=1           Rebuild even if $JOB_DB already exists.
#   SKIP_DOWNLOAD=1   Assume parquets already in JOB_PARQUET_DIR; skip curl.
#   PARALLEL=N        Concurrent download workers (default 4).
#
# Runtime is dominated by network bandwidth. ~1.75 GB so anything from
# minutes to hours depending on link quality.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=test_config.sh
source "$SCRIPT_DIR/test_config.sh"

JOB_PARQUET_DIR="${JOB_PARQUET_DIR:-$OY_REPO_ROOT/job_parquet}"
PARALLEL="${PARALLEL:-4}"

if [ ! -x "$DUCKDB_BIN" ]; then
    echo "[build_job_db] ERROR: DUCKDB_BIN '$DUCKDB_BIN' is not executable." >&2
    echo "                Build DuckDB first (e.g. make release)." >&2
    exit 2
fi

SQL_FILE="$SCRIPT_DIR/build_job_db.sql"
if [ ! -f "$SQL_FILE" ]; then
    echo "[build_job_db] ERROR: missing $SQL_FILE" >&2
    exit 2
fi

if [ -e "$JOB_DB" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "[build_job_db] $JOB_DB already exists. Set FORCE=1 to rebuild."
    "$DUCKDB_BIN" "$JOB_DB" -c "SELECT table_name FROM duckdb_tables WHERE schema_name='main' ORDER BY table_name;" || true
    exit 0
fi

# 21 file basenames (the GitHub release prefixes them with 'job_').
TABLES=(
    aka_name aka_title cast_info char_name comp_cast_type
    company_name company_type complete_cast info_type keyword
    kind_type link_type movie_companies movie_info movie_info_idx
    movie_keyword movie_link name person_info role_type title
)
BASE_URL='https://github.com/duckdb/duckdb-data/releases/download/v1.0'

mkdir -p "$JOB_PARQUET_DIR"

if [ "${SKIP_DOWNLOAD:-0}" != "1" ]; then
    echo "[build_job_db] Downloading 21 parquet files into $JOB_PARQUET_DIR (PARALLEL=$PARALLEL)"
    pids=()
    inflight=0
    for t in "${TABLES[@]}"; do
        out="$JOB_PARQUET_DIR/job_${t}.parquet"
        url="$BASE_URL/job_${t}.parquet"
        if [ -s "$out" ]; then
            echo "  [skip] $out"
            continue
        fi
        (
            echo "  [get ] $url"
            # --retry 5 to ride out flaky CDNs; --continue-at - resumes partial files.
            curl -fSL --retry 5 --retry-delay 5 --continue-at - -o "$out.part" "$url"
            mv "$out.part" "$out"
        ) &
        pids+=($!)
        inflight=$((inflight + 1))
        if [ "$inflight" -ge "$PARALLEL" ]; then
            wait -n || { echo "[build_job_db] download failed" >&2; kill "${pids[@]}" 2>/dev/null; exit 1; }
            inflight=$((inflight - 1))
        fi
    done
    wait "${pids[@]}" 2>/dev/null || true
fi

# Verify all 21 are present and non-empty.
missing=0
for t in "${TABLES[@]}"; do
    f="$JOB_PARQUET_DIR/job_${t}.parquet"
    if [ ! -s "$f" ]; then
        echo "[build_job_db] missing or empty: $f" >&2
        missing=$((missing + 1))
    fi
done
if [ "$missing" -gt 0 ]; then
    echo "[build_job_db] ERROR: $missing parquet files missing — re-run after fixing network." >&2
    exit 3
fi

echo "[build_job_db] Loading into $JOB_DB ..."
"$DUCKDB_BIN" "$JOB_DB" \
    -cmd "SET VARIABLE job_dir='$JOB_PARQUET_DIR';" \
    -f "$SQL_FILE"
echo "[build_job_db] done."
