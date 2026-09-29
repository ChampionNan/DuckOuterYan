#!/usr/bin/env bash
# ============================================================================
# DuckYanOuter auto_test — Unified Configuration (configs.sh)
# ----------------------------------------------------------------------------
# Single source of truth for all tunable parameters across the test suite.
# Sourced by: experiment_onoff.sh, build_db.sh, and run_all.sh.
#
# Override any parameter from the shell:
#     OY_THREADS=16 bash auto_test/experiment_onoff.sh
#
# Or edit the defaults below directly. Per-script CLI flags still
# work and take precedence over both this file and the env (CLI > env > config).
# ============================================================================

# Guard: idempotent source.
[ -n "${OY_CONFIG_LOADED:-}" ] && return 0
OY_CONFIG_LOADED=1

# ---------------------------------------------------------------------------
# Resolve repo root (this file lives at <repo>/auto_test/configs.sh).
# ---------------------------------------------------------------------------
_OY_CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OY_REPO_ROOT="${OY_REPO_ROOT:-$(cd "$_OY_CONFIG_DIR/.." && pwd)}"

# The experiment harness and statistics support Python 3.7+.
# Set an absolute repo-local interpreter here if the system `python3` should
# not be used.
export PYTHON_BIN="${PYTHON_BIN:-python3}"

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
export GRAPH_DB="${GRAPH_DB:-$OY_REPO_ROOT/graph_db}"
export TPCH_DB="${TPCH_DB:-$OY_REPO_ROOT/tpch_db}"
export TPCDS_DB="${TPCDS_DB:-$OY_REPO_ROOT/tpcds_db}"
# JOB DB: built externally from IMDb csv (no dbgen equivalent). Set JOB_DB env
# or pre-populate the default path before running --only job/bench/all.
export JOB_DB="${JOB_DB:-$OY_REPO_ROOT/job_db}"

# Corpus root: where experiment_onoff.sh looks for
# *.sql files. Default = auto_test/outerjoin_benchmark/benchmark/ (unique corpus).
# Override with OY_CORPUS env if needed.
export OY_CORPUS="${OY_CORPUS:-$OY_REPO_ROOT/auto_test/outerjoin_benchmark/benchmark}"

# ===========================================================================
# 3) Data scale
# ===========================================================================
# GRAPH_DATASET: which SNAP graph to use for graph R1..R10 tables.
# Options: bitcoin (24K edges), epinions (509K), google (5.1M), wiki (28.5M), dblp (1M).
export GRAPH_DATASET="${GRAPH_DATASET:-bitcoin}"

# TPC scale factors. Used by both correctness and performance scripts.
export TPCH_SF="${TPCH_SF:-100}"
export TPCDS_SF="${TPCDS_SF:-50}"

# ===========================================================================
# 4) Threading
# ===========================================================================
# Sequential multi-thread configurations; no single-thread batch.
# OY_THREADS remains a scalar override for a single configuration.
# Use OY_THREAD_COUNTS="16 32" (or "16,32") for a sweep; CLI --threads wins.
export OY_THREAD_COUNTS="${OY_THREAD_COUNTS:-${OY_THREADS:-32}}"
_oy_thread_defaults="${OY_THREAD_COUNTS//,/ }"
export OY_THREADS="${OY_THREADS:-${_oy_thread_defaults%% *}}"
unset _oy_thread_defaults

# ===========================================================================
# 5) Timeouts
# ===========================================================================
# Per-statement timeout (seconds; default 10 minutes), enforced by DuckDB's max_execution_time.
# Each process also has a scaled external `timeout` watchdog. 0 disables both.
export OY_TIMEOUT_SECS="${OY_TIMEOUT_SECS:-600}"
# Extra seconds for CLI startup and teardown around a timing batch.
export OY_BATCH_GRACE_SECS="${OY_BATCH_GRACE_SECS:-30}"

# ===========================================================================
# 6) Iteration counts
# ===========================================================================
# Positive odd number of timed runs per query (after 1 warm-up run).
# NOTE: the timing phase runs (OY_RUNS + 1) executions inside ONE duckdb process
# under ONE external timeout window. The harness keeps max_execution_time at
# OY_TIMEOUT_SECS per statement, scales the process watchdog by (OY_RUNS + 1),
# and adds a small process/serialization grace period.
# Higher OY_RUNS therefore increases total experiment time and can expose more
# timing-phase timeouts on slow (e.g. large-graph) queries.
export OY_RUNS="${OY_RUNS:-3}"

# Separate ON phase profiles at the same thread count, only for correct queries
# that select OuterYan. Timing medians remain unprofiled. CLI --no-profile opts out.
export OY_PROFILE="${OY_PROFILE:-1}"

# Save OFF/ON EXPLAIN plans plus OuterYan trace/cost artifacts. The
# experiment_onoff.sh --capture-plans flag sets this to 1 for a run.
export OY_CAPTURE_PLANS="${OY_CAPTURE_PLANS:-0}"

# Bare-query correctness emits and externally sorts the complete OFF and ON
# result multisets. Keep these potentially large temporary files on the same
# filesystem as the repository instead of the capacity-limited system /tmp.
# On the Linux server checkout at /home/data/bchenba/DuckYanOuter this resolves
# to /home/data/bchenba/DuckYanOuter/auto_test/results/tmp, backed by /home.
export OY_TMPDIR="${OY_TMPDIR:-$OY_REPO_ROOT/auto_test/results/tmp}"

# ===========================================================================
# 7) Pretty-print summary (only when sourced interactively / verbose)
# ===========================================================================
if [ "${OY_CONFIG_VERBOSE:-0}" = "1" ]; then
    {
        echo "=== auto_test config ==="
        echo "  DUCKDB_BIN       = $DUCKDB_BIN"
        echo "  GRAPH_DATASET    = $GRAPH_DATASET"
        echo "  TPCH_SF/TPCDS_SF = $TPCH_SF / $TPCDS_SF"
        echo "  OY_THREADS       = $OY_THREADS"
        echo "  OY_THREAD_COUNTS = $OY_THREAD_COUNTS (sequential)"
        echo "  TIMEOUT          = ${OY_TIMEOUT_SECS}s per statement"
        echo "  BATCH GRACE      = ${OY_BATCH_GRACE_SECS}s"
        echo "  OY_RUNS          = $OY_RUNS (median of N timed iterations)"
        echo "  CAPTURE_PLANS     = $OY_CAPTURE_PLANS"
        echo "  OY_TMPDIR         = $OY_TMPDIR"
        echo "========================="
    } >&2
fi
