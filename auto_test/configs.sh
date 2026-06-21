#!/usr/bin/env bash
# ============================================================================
# DuckYanOuter auto_test — Unified Configuration (configs.sh)
# ----------------------------------------------------------------------------
# Single source of truth for all tunable parameters across the test suite.
# Sourced by: experiment_onoff.sh, build_db.sh
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
# *.sql files. Default = auto_test/outerjoin_query/ (the unified corpus).
# Override with OY_CORPUS env if needed.
export OY_CORPUS="${OY_CORPUS:-$OY_REPO_ROOT/auto_test/outerjoin_query}"

# ===========================================================================
# 3) Data scale
# ===========================================================================
# GRAPH_DATASET: which SNAP graph to use for graph R1..R10 tables.
# Options: bitcoin (24K edges), epinions (509K), google (5.1M), wiki (28.5M), dblp (1M).
export GRAPH_DATASET="${GRAPH_DATASET:-bitcoin}"

# TPC scale factors. Used by both correctness and performance scripts.
export TPCH_SF="${TPCH_SF:-50}"
export TPCDS_SF="${TPCDS_SF:-50}"

# ===========================================================================
# 4) Threading
# ===========================================================================
# Multi-thread count for performance timing in experiment_onoff.sh.
# Each query is timed at BOTH threads=1 (single-thread) and threads=OY_THREADS.
# Valid choices: 1, 4, 8, 16, 32, 72.
export OY_THREADS="${OY_THREADS:-72}"

# ===========================================================================
# 5) Timeouts
# ===========================================================================
# Per-query timeout (seconds). Each duckdb invocation is wrapped with `timeout`.
# If a query exceeds this limit, it is killed and marked TIMEOUT. 0 disables.
export OY_TIMEOUT_SECS="${OY_TIMEOUT_SECS:-300}"

# ===========================================================================
# 6) Iteration counts
# ===========================================================================
# Fixed number of timed runs per query (after 2 warm-up runs). Median is taken.
export OY_RUNS="${OY_RUNS:-10}"

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
        echo "  TIMEOUT          = ${OY_TIMEOUT_SECS}s per query"
        echo "  OY_RUNS          = $OY_RUNS (median of N timed iterations)"
        echo "========================="
    } >&2
fi
