#!/usr/bin/env bash
# ============================================================================
# DuckYanOuter auto_test — Unified Configuration
# ----------------------------------------------------------------------------
# Single source of truth for all tunable parameters across the test suite.
# Sourced by: compare_equal_batch.sh, experiment_onoff.sh, experiment_semijoin.sh,
#             outer_yan_bench_lib.sh
#
# Override any parameter from the shell:
#     OY_THREADS=16 RSCALE=200000 bash auto_test/experiment_onoff.sh
#
# Or edit the defaults below directly. Per-script CLI flags (e.g. --rscale) still
# work and take precedence over both this file and the env (CLI > env > config).
# ============================================================================

# Guard: idempotent source.
[ -n "${OY_CONFIG_LOADED:-}" ] && return 0
OY_CONFIG_LOADED=1

# ---------------------------------------------------------------------------
# Resolve repo root (this file lives at <repo>/auto_test/test_config.sh).
# ---------------------------------------------------------------------------
_OY_CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OY_REPO_ROOT="${OY_REPO_ROOT:-$(cd "$_OY_CONFIG_DIR/.." && pwd)}"

# ===========================================================================
# 1) DuckDB binary
# ===========================================================================
# Prefer release; fall back to debug if release isn't built.
if [ -z "${DUCKDB_BIN:-}" ]; then
    if [ -x "$OY_REPO_ROOT/build/release/duckdb" ]; then
        DUCKDB_BIN="$OY_REPO_ROOT/build/release/duckdb"
    else
        DUCKDB_BIN="$OY_REPO_ROOT/build/debug/duckdb"
    fi
fi
export DUCKDB_BIN

# ===========================================================================
# 2) Database files
# ===========================================================================
export EQUIV_DB="${EQUIV_DB:-$OY_REPO_ROOT/equiv_db}"
export TPCH_DB="${TPCH_DB:-$OY_REPO_ROOT/tpch_db}"
export TPCDS_DB="${TPCDS_DB:-$OY_REPO_ROOT/tpcds_db}"
# JOB DB: built externally from IMDb csv (no dbgen equivalent). Set JOB_DB env
# or pre-populate the default path before running --only job/bench/all.
export JOB_DB="${JOB_DB:-$OY_REPO_ROOT/job_db}"

# Corpus root: where experiment_onoff.sh / experiment_semijoin.sh look for
# *.sql files. Default = auto_test/query/ (the SQLStorm-filtered + equivalence
# layout used in this project). Override with OY_CORPUS env if needed.
export OY_CORPUS="${OY_CORPUS:-$OY_REPO_ROOT/auto_test/query}"

# ===========================================================================
# 3) Data scale
# ===========================================================================
# Equivalence corpus row count (data_generation.py --total-ids,
# experiment_onoff.sh --rscale). 10000 = quick local test; 500000 = full run.
export RSCALE="${RSCALE:-1000}"

# TPC scale factors. Used by both correctness and performance scripts.
export TPCH_SF="${TPCH_SF:-0.01}"
export TPCDS_SF="${TPCDS_SF:-0.01}"

# Random seed for data_generation.py (so runs are reproducible).
export OY_SEED="${OY_SEED:-42}"

# ===========================================================================
# 4) Threading
# ===========================================================================
# Default thread count for performance timing in experiment_onoff.sh.
# 1  = single-thread, most precise (no scheduler noise) but easily times out
#      on N7+ topologies at RSCALE>=500000.
# 8  = balanced, recommended for daily runs (matches BENCH_THREADS).
# 16 = aggressive, use only on machines with 16+ physical cores.
export OY_THREADS="${OY_THREADS:-8}"

# Thread budgets used by compare_equal_batch.sh. Equiv suite is light; bench
# (TPCH/TPCDS) is heavy.
export EQUIV_THREADS="${EQUIV_THREADS:-4}"
export BENCH_THREADS="${BENCH_THREADS:-8}"

# ===========================================================================
# 5) Memory / temp budgets (compare_equal_batch.sh)
# ===========================================================================
export EQUIV_MEM="${EQUIV_MEM:-20GB}"
export BENCH_MEM="${BENCH_MEM:-100GB}"
export BENCH_TMPCAP="${BENCH_TMPCAP:-50GB}"

# ===========================================================================
# 6) Timeouts
# ===========================================================================
# Per-query soft timeout for `oy_duck` (uses /usr/bin/timeout). 0 disables.
# Affects oy_equiv_check + oy_time_min in outer_yan_bench_lib.sh.
export OY_TIMEOUT_SECS="${OY_TIMEOUT_SECS:-300}"

# Hard watchdog: SIGKILL any duckdb child running > KILL_AFTER seconds.
# Backstop for cases where soft timeout is ignored (deadlocked DuckDB).
# Set to 0 to disable.
export KILL_AFTER="${KILL_AFTER:-600}"

# Minimum cumulative timing window per query (oy_time_min in lib).
# 0 = no minimum window (just RUNS iterations). For local quick tests use 0.
export OY_MIN_SECS="${OY_MIN_SECS:-0}"

# Soft timeouts used by compare_equal_batch.sh (these wrap an entire batch).
export EQUIV_TIMEOUT="${EQUIV_TIMEOUT:-300}"
export BENCH_TIMEOUT="${BENCH_TIMEOUT:-900}"

# ===========================================================================
# 7) Iteration counts
# ===========================================================================
# Floor on number of timed runs per query in oy_time_min. Actual count grows
# until cumulative window >= OY_MIN_SECS (capped at 20000 internally).
export OY_RUNS="${OY_RUNS:-5}"

# ===========================================================================
# 8) Semijoin experiment (experiment_semijoin.sh)
# ===========================================================================
export OY_SEMI_N="${OY_SEMI_N:-1000000}"   # fact-table row count
export OY_SEMI_DOM="${OY_SEMI_DOM:-200000}" # dimension domain size
export OY_SEMI_SEL="${OY_SEMI_SEL:-0.5}"    # filter selectivity
export OY_SEMI_RUNS="${OY_SEMI_RUNS:-5}"    # min runs per query

# ===========================================================================
# 9) Pretty-print summary (only when sourced interactively / verbose)
# ===========================================================================
if [ "${OY_CONFIG_VERBOSE:-0}" = "1" ]; then
    {
        echo "=== auto_test config ==="
        echo "  DUCKDB_BIN       = $DUCKDB_BIN"
        echo "  RSCALE           = $RSCALE"
        echo "  TPCH_SF/TPCDS_SF = $TPCH_SF / $TPCDS_SF"
        echo "  OY_THREADS       = $OY_THREADS  (equiv=$EQUIV_THREADS bench=$BENCH_THREADS)"
        echo "  TIMEOUT/KILL     = ${OY_TIMEOUT_SECS}s soft / ${KILL_AFTER}s hard"
        echo "  OY_MIN_SECS      = $OY_MIN_SECS  (runs floor=$OY_RUNS)"
        echo "  semijoin         = N=$OY_SEMI_N DOM=$OY_SEMI_DOM SEL=$OY_SEMI_SEL"
        echo "========================="
    } >&2
fi
