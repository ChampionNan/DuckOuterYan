#!/usr/bin/env bash
# ============================================================================
# DuckYanOuter auto_test — Unified Configuration (configs.sh)
# ----------------------------------------------------------------------------
# Single source of truth for all tunable parameters across the test suite.
# Sourced by: experiment_onoff.sh, build_db.sh, run_all.sh, and the
# PostgreSQL-plan setup/prepare/capture scripts.
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

# Python 3.7+ is sufficient; all PGPlan tooling uses only the standard library.
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
export TPCH_SF="${TPCH_SF:-100}"
export TPCDS_SF="${TPCDS_SF:-100}"

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
# Per-statement timeout (seconds), enforced by DuckDB's max_execution_time.
# Each process also has a scaled external `timeout` watchdog. 0 disables both.
export OY_TIMEOUT_SECS="${OY_TIMEOUT_SECS:-1800}"
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
# 7) PostgreSQL plan baseline (PGPlan)
# ===========================================================================
# The normal run_all.sh workflow compares only DuckDB Original and OuterYan.
# Set RUN_PGPLAN=1 explicitly for the PostgreSQL-backed three-way experiment.
# Previous PG_REPLAY_* spellings are accepted only as compatibility aliases;
# new callers should use PGPLAN_*.
export RUN_PGPLAN="${RUN_PGPLAN:-${RUN_PG_REPLAY:-0}}"
export RUN_PG_REPLAY="$RUN_PGPLAN"

# source:   auto-download/build/install/start pinned PostgreSQL in this checkout;
# docker:   optionally run the pinned official image (host psql is not required);
# external: use PG_DSN/PSQL_BIN supplied by the caller.
export PGPLAN_SETUP="${PGPLAN_SETUP:-${PG_REPLAY_SETUP:-source}}"
export PGPLAN_VERSION="${PGPLAN_VERSION:-${PG_REPLAY_VERSION:-16.2}}"
export PGPLAN_VERSION_NUM="${PGPLAN_VERSION_NUM:-${PG_REPLAY_VERSION_NUM:-160002}}"
export PGPLAN_SOURCE_SHA256="${PGPLAN_SOURCE_SHA256:-${PG_REPLAY_SOURCE_SHA256:-2b8201047ec81acd1bad29dba278d788e7891b9c3e8232eda16bb29dec8131c7}}"
export PG_REPLAY_SETUP="$PGPLAN_SETUP"
export PG_REPLAY_VERSION="$PGPLAN_VERSION"
export PG_REPLAY_VERSION_NUM="$PGPLAN_VERSION_NUM"
export PG_REPLAY_SOURCE_SHA256="$PGPLAN_SOURCE_SHA256"

# These paths intentionally match the layout used by the original Quorion
# reproducibility launcher: <repo>/postgres contains the unpacked source and
# <repo>/postgres/postgresql is the installation prefix.
export PGPLAN_ROOT="${PGPLAN_ROOT:-${PG_REPLAY_ROOT:-$OY_REPO_ROOT/postgres}}"
export PGPLAN_SOURCE_DIR="${PGPLAN_SOURCE_DIR:-${PG_REPLAY_SOURCE_DIR:-$PGPLAN_ROOT}}"
export PGPLAN_INSTALL_DIR="${PGPLAN_INSTALL_DIR:-${PG_REPLAY_INSTALL_DIR:-$PGPLAN_ROOT/postgresql}}"
export PGPLAN_DATA_DIR="${PGPLAN_DATA_DIR:-${PG_REPLAY_DATA_DIR:-$PGPLAN_INSTALL_DIR/data}}"
export PGPLAN_LOG_FILE="${PGPLAN_LOG_FILE:-${PG_REPLAY_LOG_FILE:-$PGPLAN_INSTALL_DIR/postgresql.log}}"
export PGPLAN_BUILD_JOBS="${PGPLAN_BUILD_JOBS:-${PG_REPLAY_BUILD_JOBS:-${JOBS:-8}}}"
export PGPLAN_FORCE_DATA="${PGPLAN_FORCE_DATA:-${PG_REPLAY_FORCE_DATA:-0}}"
export PG_REPLAY_ROOT="$PGPLAN_ROOT"
export PG_REPLAY_SOURCE_DIR="$PGPLAN_SOURCE_DIR"
export PG_REPLAY_INSTALL_DIR="$PGPLAN_INSTALL_DIR"
export PG_REPLAY_DATA_DIR="$PGPLAN_DATA_DIR"
export PG_REPLAY_LOG_FILE="$PGPLAN_LOG_FILE"
export PG_REPLAY_BUILD_JOBS="$PGPLAN_BUILD_JOBS"
export PG_REPLAY_FORCE_DATA="$PGPLAN_FORCE_DATA"

# The managed source and Docker modes use a dedicated loopback endpoint. The
# PG_REPLAY_CONTAINER_* spellings remain compatibility inputs.
export PGPLAN_HOST="${PGPLAN_HOST:-${PG_REPLAY_HOST:-127.0.0.1}}"
export PGPLAN_PORT="${PGPLAN_PORT:-${PG_REPLAY_PORT:-${PGPLAN_CONTAINER_PORT:-${PG_REPLAY_CONTAINER_PORT:-55432}}}}"
export PGPLAN_DATABASE="${PGPLAN_DATABASE:-${PG_REPLAY_DATABASE:-${PGPLAN_CONTAINER_DATABASE:-${PG_REPLAY_CONTAINER_DATABASE:-duckyan_tpch}}}}"
export PGPLAN_USER="${PGPLAN_USER:-${PG_REPLAY_USER:-${PGPLAN_CONTAINER_USER:-${PG_REPLAY_CONTAINER_USER:-postgres}}}}"
export PGPLAN_PASSWORD_FILE="${PGPLAN_PASSWORD_FILE:-$PGPLAN_INSTALL_DIR/.pgplan-password}"
_oy_pgplan_general_password="${PGPLAN_PASSWORD:-${PG_REPLAY_PASSWORD:-}}"
_oy_pgplan_container_override="${PGPLAN_CONTAINER_PASSWORD:-${PG_REPLAY_CONTAINER_PASSWORD:-}}"
_OY_PGPLAN_GENERAL_PASSWORD_FROM_FILE=0
_OY_PGPLAN_CONTAINER_PASSWORD_FROM_FILE=0

# Reading an already-created private credential is side-effect free. Creating
# it, repairing its mode, and creating its parent belong to setup_pg.sh: a run
# whose plans all hit the persistent cache must not need a writable PostgreSQL
# installation path merely because it sources this configuration file.
_pgplan_read_existing_managed_password() {
    local candidate mode
    [ -f "$PGPLAN_PASSWORD_FILE" ] && [ ! -L "$PGPLAN_PASSWORD_FILE" ] && \
        [ -O "$PGPLAN_PASSWORD_FILE" ] && [ -r "$PGPLAN_PASSWORD_FILE" ] || return 1
    if mode="$(stat -c '%a' "$PGPLAN_PASSWORD_FILE" 2>/dev/null)"; then
        :
    elif mode="$(stat -f '%Lp' "$PGPLAN_PASSWORD_FILE" 2>/dev/null)"; then
        :
    else
        return 1
    fi
    case "$mode" in 400|600) ;; *) return 1 ;; esac
    candidate="$(sed -n '1p' "$PGPLAN_PASSWORD_FILE")" || return 1
    [[ "$candidate" =~ ^[0-9a-f]{64}$ ]] || return 1
    printf '%s' "$candidate"
}

_oy_pgplan_file_password=""
case "$PGPLAN_SETUP" in
    source)
        if [ -z "$_oy_pgplan_general_password" ] && \
                _oy_pgplan_file_password="$(_pgplan_read_existing_managed_password)"; then
            _oy_pgplan_general_password="$_oy_pgplan_file_password"
            _OY_PGPLAN_GENERAL_PASSWORD_FROM_FILE=1
        fi
        ;;
    docker)
        if [ -z "$_oy_pgplan_general_password" ] && \
                [ -n "$_oy_pgplan_container_override" ]; then
            _oy_pgplan_general_password="$_oy_pgplan_container_override"
        fi
        if [ -z "$_oy_pgplan_general_password" ] && \
                _oy_pgplan_file_password="$(_pgplan_read_existing_managed_password)"; then
            _oy_pgplan_general_password="$_oy_pgplan_file_password"
            _OY_PGPLAN_GENERAL_PASSWORD_FROM_FILE=1
        fi
        ;;
esac

case "$PGPLAN_SETUP" in
    source|docker)
        PGPLAN_PASSWORD="$_oy_pgplan_general_password"
        PG_REPLAY_PASSWORD="$PGPLAN_PASSWORD"
        PGPLAN_CONTAINER_PASSWORD="$_oy_pgplan_container_override"
        if [ -z "$PGPLAN_CONTAINER_PASSWORD" ]; then
            PGPLAN_CONTAINER_PASSWORD="$PGPLAN_PASSWORD"
            _OY_PGPLAN_CONTAINER_PASSWORD_FROM_FILE="$_OY_PGPLAN_GENERAL_PASSWORD_FROM_FILE"
        fi
        PG_REPLAY_CONTAINER_PASSWORD="$PGPLAN_CONTAINER_PASSWORD"
        export PGPLAN_PASSWORD PG_REPLAY_PASSWORD
        export PGPLAN_CONTAINER_PASSWORD PG_REPLAY_CONTAINER_PASSWORD
        ;;
    *)
        # External mode retains its historical configuration aliases and
        # fallback; configs.sh does not apply it to the caller's connection.
        PGPLAN_PASSWORD="${PGPLAN_PASSWORD:-${PG_REPLAY_PASSWORD:-${PGPLAN_CONTAINER_PASSWORD:-${PG_REPLAY_CONTAINER_PASSWORD:-duckyan}}}}"
        PG_REPLAY_PASSWORD="$PGPLAN_PASSWORD"
        PGPLAN_CONTAINER_PASSWORD="${PGPLAN_CONTAINER_PASSWORD:-${PG_REPLAY_CONTAINER_PASSWORD:-$PGPLAN_PASSWORD}}"
        PG_REPLAY_CONTAINER_PASSWORD="$PGPLAN_CONTAINER_PASSWORD"
        export PGPLAN_PASSWORD PG_REPLAY_PASSWORD
        export PGPLAN_CONTAINER_PASSWORD PG_REPLAY_CONTAINER_PASSWORD
        ;;
esac
unset _oy_pgplan_general_password _oy_pgplan_container_override _oy_pgplan_file_password

# Materialize the managed credential only from an explicit setup path. The
# function is intentionally defined by configs.sh so setup_pg.sh and the
# standalone local-container loader share the same secure implementation.
pgplan_ensure_managed_password() {
    local mode="${1:-$PGPLAN_SETUP}" candidate from_file generated
    case "$mode" in
        source)
            candidate="${PGPLAN_PASSWORD:-}"
            from_file="${_OY_PGPLAN_GENERAL_PASSWORD_FROM_FILE:-0}"
            ;;
        docker)
            candidate="${PGPLAN_CONTAINER_PASSWORD:-${PGPLAN_PASSWORD:-}}"
            from_file="${_OY_PGPLAN_CONTAINER_PASSWORD_FROM_FILE:-0}"
            ;;
        *) return 0 ;;
    esac

    if [ -z "$candidate" ]; then
        mkdir -p "$PGPLAN_INSTALL_DIR" || {
            echo "ERROR: could not create managed PostgreSQL credential directory: $PGPLAN_INSTALL_DIR" >&2
            return 1
        }
        if [ ! -e "$PGPLAN_PASSWORD_FILE" ] && [ ! -L "$PGPLAN_PASSWORD_FILE" ]; then
            generated="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')" || return 1
            [[ "$generated" =~ ^[0-9a-f]{64}$ ]] || {
                echo "ERROR: could not generate a private PostgreSQL password" >&2
                return 1
            }
            (umask 077; set -o noclobber; printf '%s\n' "$generated" \
                > "$PGPLAN_PASSWORD_FILE") 2>/dev/null || true
        fi
        from_file=1
    fi

    if [ "$from_file" = "1" ]; then
        if [ ! -f "$PGPLAN_PASSWORD_FILE" ] || [ -L "$PGPLAN_PASSWORD_FILE" ] || \
                [ ! -O "$PGPLAN_PASSWORD_FILE" ]; then
            echo "ERROR: PGPLAN_PASSWORD_FILE must be a regular, non-symlink file owned by the current user: $PGPLAN_PASSWORD_FILE" >&2
            return 1
        fi
        chmod 600 "$PGPLAN_PASSWORD_FILE" || return 1
        candidate="$(sed -n '1p' "$PGPLAN_PASSWORD_FILE")" || return 1
        if [[ ! "$candidate" =~ ^[0-9a-f]{64}$ ]]; then
            echo "ERROR: generated PGPLAN_PASSWORD_FILE is malformed: $PGPLAN_PASSWORD_FILE" >&2
            return 1
        fi
    fi
    [ -n "$candidate" ] || {
        echo "ERROR: managed PostgreSQL setup requires a nonempty password" >&2
        return 1
    }
    case "$candidate" in
        *$'\n'*|*$'\r'*)
            echo "ERROR: managed PostgreSQL password must not contain a newline" >&2
            return 1
            ;;
    esac

    case "$mode" in
        source)
            PGPLAN_PASSWORD="$candidate"
            PG_REPLAY_PASSWORD="$candidate"
            if [ -z "${PGPLAN_CONTAINER_PASSWORD:-}" ]; then
                PGPLAN_CONTAINER_PASSWORD="$candidate"
                PG_REPLAY_CONTAINER_PASSWORD="$candidate"
            fi
            _OY_PGPLAN_GENERAL_PASSWORD_FROM_FILE="$from_file"
            ;;
        docker)
            PGPLAN_CONTAINER_PASSWORD="$candidate"
            PG_REPLAY_CONTAINER_PASSWORD="$candidate"
            if [ -z "${PGPLAN_PASSWORD:-}" ]; then
                PGPLAN_PASSWORD="$candidate"
                PG_REPLAY_PASSWORD="$candidate"
            fi
            _OY_PGPLAN_CONTAINER_PASSWORD_FROM_FILE="$from_file"
            ;;
    esac
    PGPASSWORD="$candidate"
    export PGPLAN_PASSWORD PG_REPLAY_PASSWORD
    export PGPLAN_CONTAINER_PASSWORD PG_REPLAY_CONTAINER_PASSWORD PGPASSWORD
}
export PGPLAN_CONTAINER_NAME="${PGPLAN_CONTAINER_NAME:-${PG_REPLAY_CONTAINER_NAME:-duckyan-pg16-2}}"
export PGPLAN_CONTAINER_IMAGE="${PGPLAN_CONTAINER_IMAGE:-${PG_REPLAY_CONTAINER_IMAGE:-postgres:$PGPLAN_VERSION}}"
export PGPLAN_CONTAINER_PORT="${PGPLAN_CONTAINER_PORT:-${PG_REPLAY_CONTAINER_PORT:-$PGPLAN_PORT}}"
export PGPLAN_CONTAINER_DATABASE="${PGPLAN_CONTAINER_DATABASE:-${PG_REPLAY_CONTAINER_DATABASE:-$PGPLAN_DATABASE}}"
export PGPLAN_CONTAINER_USER="${PGPLAN_CONTAINER_USER:-${PG_REPLAY_CONTAINER_USER:-$PGPLAN_USER}}"
export PG_REPLAY_HOST="$PGPLAN_HOST"
export PG_REPLAY_PORT="$PGPLAN_PORT"
export PG_REPLAY_DATABASE="$PGPLAN_DATABASE"
export PG_REPLAY_USER="$PGPLAN_USER"
export PG_REPLAY_CONTAINER_NAME="$PGPLAN_CONTAINER_NAME"
export PG_REPLAY_CONTAINER_IMAGE="$PGPLAN_CONTAINER_IMAGE"
export PG_REPLAY_CONTAINER_PORT="$PGPLAN_CONTAINER_PORT"
export PG_REPLAY_CONTAINER_DATABASE="$PGPLAN_CONTAINER_DATABASE"
export PG_REPLAY_CONTAINER_USER="$PGPLAN_CONTAINER_USER"

export PG_DSN="${PG_DSN:-host=$PGPLAN_HOST port=$PGPLAN_PORT dbname=$PGPLAN_DATABASE user=$PGPLAN_USER}"
case "$PGPLAN_SETUP" in
    source)
        # The managed endpoint and role always use the per-installation secret;
        # do not let an unrelated ambient libpq password select another value.
        if [ -n "$PGPLAN_PASSWORD" ]; then
            export PGPASSWORD="$PGPLAN_PASSWORD"
        else
            unset PGPASSWORD
        fi
        ;;
    docker)
        if [ -n "$PGPLAN_CONTAINER_PASSWORD" ]; then
            export PGPASSWORD="$PGPLAN_CONTAINER_PASSWORD"
        else
            unset PGPASSWORD
        fi
        ;;
esac

if [ -z "${PSQL_BIN:-}" ]; then
    case "$PGPLAN_SETUP" in
        source)
            PSQL_BIN="$PGPLAN_INSTALL_DIR/bin/psql"
            ;;
        docker)
            PSQL_BIN="$OY_REPO_ROOT/auto_test/pgplan/docker_psql.sh"
            ;;
        external)
            PSQL_BIN="psql"
            ;;
    esac
fi
export PSQL_BIN

# Corpus-wide PGPlan defaults. TPC-H plan selection uses SF0.01; the other
# families use isolated, row-capped schemas derived from their DuckDB schemas.
export PGPLAN_CORPUS="${PGPLAN_CORPUS:-$OY_REPO_ROOT/auto_test/outerjoin_query}"
export PGPLAN_SAMPLE_ROWS="${PGPLAN_SAMPLE_ROWS:-1000}"
# Normal runs retain validated PostgreSQL artifacts across result directories.
# The cache key mirrors the corpus-relative query stem (family/name.pg.json).
export PGPLAN_PLAN_CACHE="${PGPLAN_PLAN_CACHE:-$OY_REPO_ROOT/auto_test/pgplan/plans}"
# `both` checks Original against PGPlan and OuterYan. `pgplan-only` omits the
# OuterYan result comparison; `none` performs plan verification and timing only.
export PGPLAN_COMPARISON_MODE="${PGPLAN_COMPARISON_MODE:-both}"
case "$PGPLAN_COMPARISON_MODE" in
    both|pgplan-only|none) ;;
    *)
        echo "ERROR: PGPLAN_COMPARISON_MODE must be both, pgplan-only, or none" >&2
        return 1 2>/dev/null || exit 1
        ;;
esac
# Exact result comparison defaults to the same target DuckDB database used for
# EXPLAIN/signature validation and timing. Set this to `bounded` explicitly to
# build deterministic small correctness databases for a quicker diagnostic
# run; bounded mode is not the default correctness claim. `reuse` skips a new
# comparison only after experiment.sh validates a sealed target-scale receipt
# from the matching per-query run below PGPLAN_CORRECTNESS_FROM.
export PGPLAN_REUSE_FROM="${PGPLAN_REUSE_FROM:-}"
export PGPLAN_CORRECTNESS_MODE="${PGPLAN_CORRECTNESS_MODE:-${PG_REPLAY_CORRECTNESS_MODE:-target}}"
export PGPLAN_CORRECTNESS_FROM="${PGPLAN_CORRECTNESS_FROM:-${PG_REPLAY_CORRECTNESS_FROM:-}}"
if [ -n "$PGPLAN_REUSE_FROM" ]; then
    PGPLAN_CORRECTNESS_MODE="reuse"
    PGPLAN_CORRECTNESS_FROM="$PGPLAN_REUSE_FROM"
    export PGPLAN_CORRECTNESS_MODE PGPLAN_CORRECTNESS_FROM
fi
case "$PGPLAN_CORRECTNESS_MODE" in
    target|bounded|reuse) ;;
    *)
        echo "ERROR: PGPLAN_CORRECTNESS_MODE must be target, bounded, or reuse" >&2
        return 1 2>/dev/null || exit 1
        ;;
esac
# Corpus root from a previous target-mode run. It is required only in `reuse`
# mode; corpus_experiment.sh resolves and validates each per-query directory
# beneath <root>/runs/<family>/<query-label> without falling back to fresh
# correctness when a receipt is missing or stale.
if [ "$PGPLAN_CORRECTNESS_MODE" = "reuse" ] && [ -z "$PGPLAN_CORRECTNESS_FROM" ]; then
    echo "ERROR: PGPLAN_CORRECTNESS_FROM is required when PGPLAN_CORRECTNESS_MODE=reuse" >&2
    return 1 2>/dev/null || exit 1
fi
export PGPLAN_CORRECTNESS_GRAPH_ROWS="${PGPLAN_CORRECTNESS_GRAPH_ROWS:-500}"
export PGPLAN_CORRECTNESS_JOB_ROWS="${PGPLAN_CORRECTNESS_JOB_ROWS:-1000}"
export PGPLAN_CORRECTNESS_MAX_RESULT_ROWS="${PGPLAN_CORRECTNESS_MAX_RESULT_ROWS:-2000000}"
export PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS="${PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS:-30}"
# Retained as a one-query compatibility/manual-capture default.
export PGPLAN_QUERY="${PGPLAN_QUERY:-${PG_REPLAY_QUERY:-$OY_REPO_ROOT/auto_test/outerjoin_benchmark/industry_inspired/tpch/oy_th_real_supplier_right.sql}}"
export PGPLAN_EXECUTION_DB="${PGPLAN_EXECUTION_DB:-${PG_REPLAY_EXECUTION_DB:-$TPCH_DB}}"
export PGPLAN_RUNS="${PGPLAN_RUNS:-${PG_REPLAY_RUNS:-$OY_RUNS}}"
export PGPLAN_THREADS="${PGPLAN_THREADS:-${PG_REPLAY_THREADS:-$OY_THREADS}}"
# PostgreSQL uses plain EXPLAIN without ANALYZE. Bound optimizer time
# separately from DuckDB execution so an expensive plan search can be skipped.
export PGPLAN_CAPTURE_TIMEOUT_SECS="${PGPLAN_CAPTURE_TIMEOUT_SECS:-${PG_REPLAY_CAPTURE_TIMEOUT_SECS:-300}}"
export PGPLAN_TIMEOUT_SECS="${PGPLAN_TIMEOUT_SECS:-${PG_REPLAY_TIMEOUT_SECS:-$OY_TIMEOUT_SECS}}"
export PGPLAN_TIMEOUT_GRACE="${PGPLAN_TIMEOUT_GRACE:-${PG_REPLAY_TIMEOUT_GRACE:-$OY_BATCH_GRACE_SECS}}"
export PGPLAN_TMPDIR="${PGPLAN_TMPDIR:-${PG_REPLAY_TMPDIR:-$OY_TMPDIR}}"
export PG_REPLAY_QUERY="$PGPLAN_QUERY"
export PG_REPLAY_EXECUTION_DB="$PGPLAN_EXECUTION_DB"
export PG_REPLAY_PLAN_CACHE="$PGPLAN_PLAN_CACHE"
export PG_REPLAY_COMPARISON_MODE="$PGPLAN_COMPARISON_MODE"
export PG_REPLAY_CORRECTNESS_MODE="$PGPLAN_CORRECTNESS_MODE"
export PG_REPLAY_CORRECTNESS_FROM="$PGPLAN_CORRECTNESS_FROM"
export PG_REPLAY_CORRECTNESS_GRAPH_ROWS="$PGPLAN_CORRECTNESS_GRAPH_ROWS"
export PG_REPLAY_CORRECTNESS_JOB_ROWS="$PGPLAN_CORRECTNESS_JOB_ROWS"
export PG_REPLAY_CORRECTNESS_MAX_RESULT_ROWS="$PGPLAN_CORRECTNESS_MAX_RESULT_ROWS"
export PG_REPLAY_CORRECTNESS_QUERY_TIMEOUT_SECS="$PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS"
export PG_REPLAY_RUNS="$PGPLAN_RUNS"
export PG_REPLAY_THREADS="$PGPLAN_THREADS"
export PG_REPLAY_CAPTURE_TIMEOUT_SECS="$PGPLAN_CAPTURE_TIMEOUT_SECS"
export PG_REPLAY_TIMEOUT_SECS="$PGPLAN_TIMEOUT_SECS"
export PG_REPLAY_TIMEOUT_GRACE="$PGPLAN_TIMEOUT_GRACE"
export PG_REPLAY_TMPDIR="$PGPLAN_TMPDIR"

# ===========================================================================
# 8) Pretty-print summary (only when sourced interactively / verbose)
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
        echo "  RUN_PGPLAN        = $RUN_PGPLAN"
        echo "  PGPLAN_SETUP      = $PGPLAN_SETUP"
        echo "  PGPLAN_PREFIX     = $PGPLAN_INSTALL_DIR"
        echo "  PGPLAN_CORPUS     = $PGPLAN_CORPUS"
        echo "  PGPLAN_SAMPLE_ROWS = $PGPLAN_SAMPLE_ROWS"
        echo "  PGPLAN_CORRECTNESS_MODE = $PGPLAN_CORRECTNESS_MODE"
        if [ "$PGPLAN_CORRECTNESS_MODE" = "reuse" ]; then
            echo "  PGPLAN_CORRECTNESS_FROM = $PGPLAN_CORRECTNESS_FROM"
        fi
        if [ -n "$PGPLAN_REUSE_FROM" ]; then
            echo "  PGPLAN_REUSE_FROM = $PGPLAN_REUSE_FROM (plans + correctness)"
        fi
        echo "  PGPLAN_CORRECTNESS_ROWS = graph:$PGPLAN_CORRECTNESS_GRAPH_ROWS job:$PGPLAN_CORRECTNESS_JOB_ROWS"
        echo "  PGPLAN_CORRECTNESS_MAX_ROWS = $PGPLAN_CORRECTNESS_MAX_RESULT_ROWS"
        echo "  PGPLAN_CAPTURE_TIMEOUT = ${PGPLAN_CAPTURE_TIMEOUT_SECS}s"
        if [ "$PGPLAN_SETUP" = "external" ]; then
            echo "  PG endpoint       = external PG_DSN (redacted)"
        else
            echo "  PG endpoint       = $PGPLAN_HOST:$PGPLAN_PORT/$PGPLAN_DATABASE"
        fi
        echo "========================="
    } >&2
fi
