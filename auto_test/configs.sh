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
# Resolve the scale before the default path; explicit paths always win. A path
# identifies one dataset and is never renamed/resized merely by changing SF.
export TPCH_SF="${TPCH_SF:-50}"
export TPCDS_SF="${TPCDS_SF:-50}"
export GRAPH_DB="${GRAPH_DB:-$OY_REPO_ROOT/graph_db}"
# The active mixed Graph corpus routes its 16 dataset-qualified queries here.
export GRAPH_EPINIONS_DB="${GRAPH_EPINIONS_DB:-$OY_REPO_ROOT/graph_epinions.duckdb}"
export TPCH_DB="${TPCH_DB:-$OY_REPO_ROOT/tpch_${TPCH_SF}.duckdb}"
export TPCDS_DB="${TPCDS_DB:-$OY_REPO_ROOT/tpcds_${TPCDS_SF}.duckdb}"
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

# TPC scale factors and their scale-qualified file defaults are set above.
# Existing files are reused; changing SF never resizes an explicit *_DB path.

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
# Independent per-engine statement limits (seconds; default 10 minutes each).
# Fixed benchmark protocol (20261011): 600 s for EACH execution on EACH engine,
# not for all five timed runs together. Either-side timeouts are excluded from
# performance statistics; raw statuses remain available for diagnostics.
# OY_TIMEOUT_SECS remains a common override; engine-specific values take precedence.
# Each process also has a scaled external `timeout` watchdog. 0 disables both.
export OY_TIMEOUT_SECS="${OY_TIMEOUT_SECS:-600}"
export OY_DUCKDB_TIMEOUT_SECS="${OY_DUCKDB_TIMEOUT_SECS:-$OY_TIMEOUT_SECS}"
export OY_OUTERYAN_TIMEOUT_SECS="${OY_OUTERYAN_TIMEOUT_SECS:-$OY_TIMEOUT_SECS}"
# Extra seconds for CLI startup and teardown around a timing batch.
export OY_BATCH_GRACE_SECS="${OY_BATCH_GRACE_SECS:-30}"

# ===========================================================================
# 6) Iteration counts
# ===========================================================================
# Positive odd number of timed runs per query/configuration; report their median.
# Default: five unprofiled runs after warm-up/profiling. CLI --runs overrides this.
# NOTE: each side runs (OY_RUNS + 1 + OY_PROFILE) executions in ONE duckdb process
# under ONE external timeout window. The harness keeps max_execution_time at
# OY_TIMEOUT_SECS per statement, scales the watchdog by that execution count,
# and adds a small process/serialization grace period.
# Higher OY_RUNS therefore increases total experiment time and can expose more
# timing-phase timeouts on slow (e.g. large-graph) queries.
export OY_RUNS="${OY_RUNS:-5}"
export OY_CHECK_CORRECTNESS="${OY_CHECK_CORRECTNESS:-1}"

# Each side runs one warm-up, one optional profile, then unprofiled timing in the
# same process. The optimizer and execution phases share that profile sample.
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
        echo "  TPCH_DB          = $TPCH_DB"
        echo "  TPCDS_DB         = $TPCDS_DB"
        echo "  OY_THREADS       = $OY_THREADS"
        echo "  OY_THREAD_COUNTS = $OY_THREAD_COUNTS (sequential)"
        echo "  TIMEOUT          = DuckDB ${OY_DUCKDB_TIMEOUT_SECS}s / OuterYan ${OY_OUTERYAN_TIMEOUT_SECS}s per statement"
        echo "  BATCH GRACE      = ${OY_BATCH_GRACE_SECS}s"
        echo "  OY_RUNS          = $OY_RUNS (1 = first post-warm-up sample; odd N >1 = median)"
        echo "  CHECK_CORRECTNESS = $OY_CHECK_CORRECTNESS (0 = NOT-CHECKED)"
        echo "  CAPTURE_PLANS     = $OY_CAPTURE_PLANS"
        echo "  OY_TMPDIR         = $OY_TMPDIR"
        echo "========================="
    } >&2
fi
