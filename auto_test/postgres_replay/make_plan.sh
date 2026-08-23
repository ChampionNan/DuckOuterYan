#!/usr/bin/env bash
# Capture one PostgreSQL 16.2 logical join tree without executing the query.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="$SCRIPT_DIR/../configs.sh"
# shellcheck source=../configs.sh
source "$CONFIG_PATH"
PSQL_BIN="${PSQL_BIN:-psql}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PG_DSN="${PG_DSN:-}"
QUERY=""
OUT=""
EXPECTED_PG_VERSION="${PGPLAN_VERSION_NUM:-160002}"
PG_SCHEMA="public"
PLAN_DATA="tpch-sf0.01"
CAPTURE_TIMEOUT_SECS="${PGPLAN_CAPTURE_TIMEOUT_SECS:-${PG_REPLAY_CAPTURE_TIMEOUT_SECS:-300}}"

usage() {
    cat <<'USAGE'
Usage:
  make_plan.sh --pg-dsn DSN --query FILE --out FILE \
      [--pg-schema public] [--plan-data tpch-sf0.01] \
      [--expected-pg-version 160002] [--capture-timeout SECONDS]

Environment overrides:
  Defaults are sourced from auto_test/configs.sh. PG_DSN, PSQL_BIN,
  PYTHON_BIN, and PGPLAN_VERSION_NUM remain overridable.

The query must be one SELECT statement. It is passed only to EXPLAIN (without
ANALYZE) inside a read-only transaction. PostgreSQL planner settings must have
their compiled defaults; max_parallel_workers_per_gather=0 and the requested
non-public plan schema's deterministic search_path are the sole plan-affecting
overrides. statement_timeout only bounds planner wall time.
The default plain-EXPLAIN optimizer timeout is PGPLAN_CAPTURE_TIMEOUT_SECS
(300 seconds); 0 disables it. A timeout exits with status 124 and writes no
artifact.
USAGE
}

die() {
    echo "ERROR: $*" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --pg-dsn)
            [ $# -ge 2 ] || die "$1 requires a value"
            PG_DSN="$2"
            shift 2
            ;;
        --query)
            [ $# -ge 2 ] || die "$1 requires a value"
            QUERY="$2"
            shift 2
            ;;
        --pg-schema)
            [ $# -ge 2 ] || die "$1 requires a value"
            PG_SCHEMA="$2"
            shift 2
            ;;
        --plan-data)
            [ $# -ge 2 ] || die "$1 requires a value"
            PLAN_DATA="$2"
            shift 2
            ;;
        --out)
            [ $# -ge 2 ] || die "$1 requires a value"
            OUT="$2"
            shift 2
            ;;
        --expected-pg-version)
            [ $# -ge 2 ] || die "$1 requires a value"
            EXPECTED_PG_VERSION="$2"
            shift 2
            ;;
        --timeout|--capture-timeout)
            [ $# -ge 2 ] || die "$1 requires a value"
            CAPTURE_TIMEOUT_SECS="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown argument: $1"
            ;;
    esac
done

[ -n "$PG_DSN" ] || die "--pg-dsn is required (or set PG_DSN)"
[ -n "$QUERY" ] || die "--query is required"
[ -f "$QUERY" ] || die "query file does not exist: $QUERY"
[ -n "$OUT" ] || die "--out is required"
[ "$EXPECTED_PG_VERSION" = "160002" ] || \
    die "PGPlan v1 is pinned to expected server_version_num 160002"
[[ "$CAPTURE_TIMEOUT_SECS" =~ ^[0-9]+$ ]] || \
    die "capture timeout must be a non-negative integer"

if [[ "$PSQL_BIN" == */* ]]; then
    [ -x "$PSQL_BIN" ] || die "PSQL_BIN is not executable: $PSQL_BIN"
else
    command -v "$PSQL_BIN" >/dev/null 2>&1 || die "psql not found: $PSQL_BIN"
fi
if [[ "$PYTHON_BIN" == */* ]]; then
    [ -x "$PYTHON_BIN" ] || die "PYTHON_BIN is not executable: $PYTHON_BIN"
else
    command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "python3 not found: $PYTHON_BIN"
fi
if "$PYTHON_BIN" -c \
    'import os,sys; raise SystemExit(0 if os.path.realpath(sys.argv[1]) == os.path.realpath(sys.argv[2]) else 1)' \
    "$QUERY" "$OUT"; then
    die "--out must not overwrite the input query file"
fi

TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/duckyan-pg-plan.XXXXXX")"
cleanup() {
    local rc=$?
    if [ -n "${TEMP_ROOT:-}" ] && [ -d "$TEMP_ROOT" ]; then
        rm -rf -- "$TEMP_ROOT"
    fi
    return "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

CAPTURE_SQL="$TEMP_ROOT/capture.sql"
RAW_PLAN="$TEMP_ROOT/explain.json"
QUERY_SNAPSHOT="$TEMP_ROOT/query.sql"

# Read the source once. Both EXPLAIN generation and the artifact hash use this
# immutable snapshot, so an editor/autosave cannot pair query A's plan with
# query B's digest.
cp -- "$QUERY" "$QUERY_SNAPSHOT"

# This also validates that the file is one SELECT. Keeping SQL generation in
# Python gives capture and artifact hashing exactly one canonicalization rule.
"$PYTHON_BIN" "$SCRIPT_DIR/normalize_plan.py" \
    --emit-explain-sql --query "$QUERY_SNAPSHOT" \
    --pg-schema "$PG_SCHEMA" --plan-data "$PLAN_DATA" \
    --capture-timeout-seconds "$CAPTURE_TIMEOUT_SECS" > "$CAPTURE_SQL"

ACTUAL_VERSION="$({
    "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
        --command="SELECT current_setting('server_version_num');"
} | tr -d '[:space:]')"
[ "$ACTUAL_VERSION" = "$EXPECTED_PG_VERSION" ] || \
    die "PostgreSQL server_version_num mismatch: expected $EXPECTED_PG_VERSION, got ${ACTUAL_VERSION:-<empty>}"

# Fail early with useful names if a cost constant, join-method toggle, GEQO
# option, collapse limit, or other Query Tuning setting differs from the PG
# 16.2 compiled default. EXPLAIN SETTINGS is checked again by the normalizer.
NONDEFAULT_SETTINGS="$({
    "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --command="
        SELECT name || '=' || setting || ' (compiled default=' || boot_val || ')'
        FROM pg_settings
        WHERE category LIKE 'Query Tuning%'
          AND name <> 'max_parallel_workers_per_gather'
          AND setting IS DISTINCT FROM boot_val
        ORDER BY name;"
})"
if [ -n "$NONDEFAULT_SETTINGS" ]; then
    {
        echo "ERROR: PostgreSQL Query Tuning settings are not at compiled defaults:"
        echo "$NONDEFAULT_SETTINGS"
    } >&2
    exit 2
fi

CAPTURE_STDERR="$TEMP_ROOT/capture.stderr"
if "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --set=VERBOSITY=verbose \
        --dbname="$PG_DSN" --file="$CAPTURE_SQL" \
        > "$RAW_PLAN" 2> "$CAPTURE_STDERR"; then
    [ ! -s "$CAPTURE_STDERR" ] || cat "$CAPTURE_STDERR" >&2
else
    capture_rc=$?
    cat "$CAPTURE_STDERR" >&2
    if [ "$CAPTURE_TIMEOUT_SECS" -gt 0 ] && \
            grep -Eq '(^|[^0-9])57014([^0-9]|$)' "$CAPTURE_STDERR"; then
        echo "[PGPLAN] SKIP capture_timeout seconds=$CAPTURE_TIMEOUT_SECS" >&2
        exit 124
    fi
    exit "$capture_rc"
fi
[ -s "$RAW_PLAN" ] || die "psql returned an empty EXPLAIN document"

"$PYTHON_BIN" "$SCRIPT_DIR/normalize_plan.py" --normalize \
    --query "$QUERY_SNAPSHOT" \
    --pg-schema "$PG_SCHEMA" \
    --plan-data "$PLAN_DATA" \
    --explain-json "$RAW_PLAN" \
    --version-num "$ACTUAL_VERSION" \
    --out "$OUT"

echo "[PGPLAN] wrote $OUT"
echo "[PGPLAN] PostgreSQL=$ACTUAL_VERSION schema=$PG_SCHEMA data=$PLAN_DATA parallel_workers=0"
