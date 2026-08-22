#!/usr/bin/env bash
# Load the exact TPC-H SF0.01 plan-selection dataset into PostgreSQL 16.2.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PSQL_BIN_WAS_SET="${PSQL_BIN+x}"
# shellcheck source=../configs.sh
source "$SCRIPT_DIR/../configs.sh"
PSQL_BIN="${PSQL_BIN:-psql}"
PG_DSN="${PG_DSN:-}"
DUCKDB_BIN="${DUCKDB_BIN:-}"
DATA_DIR="${TPCH_DATA_DIR:-}"
FORCE=0
LOCAL_CONTAINER=0
EXPECTED_PG_VERSION="${PGPLAN_VERSION_NUM:-160002}"
CONTAINER_NAME="${PGPLAN_CONTAINER_NAME:-duckyan-pg16-2}"
CONTAINER_PORT="${PGPLAN_CONTAINER_PORT:-55432}"
CONTAINER_DATABASE="${PGPLAN_CONTAINER_DATABASE:-duckyan_tpch}"
CONTAINER_USER="${PGPLAN_CONTAINER_USER:-postgres}"
CONTAINER_PASSWORD="${PGPLAN_CONTAINER_PASSWORD:-duckyan}"
CONTAINER_IMAGE="${PGPLAN_CONTAINER_IMAGE:-postgres:16.2}"
PG_DSN_EXPLICIT=0
SOURCE_ARG=""

TABLES=(region nation supplier customer part partsupp orders lineitem)
CONTAINER_STARTED=0
KEEP_CONTAINER=0

usage() {
    cat <<'USAGE'
Usage:
  prepare_tpch_pg.sh --pg-dsn DSN [--data-dir DIR | --duckdb-bin PATH] [--force]
  prepare_tpch_pg.sh --local-container [--container-name NAME] [--port PORT]
      [--data-dir DIR | --duckdb-bin PATH] [--force]

Data sources:
  --data-dir DIR     Existing region/nation/.../lineitem .tbl or .csv files.
  --duckdb-bin PATH  Generate SF0.01 with DuckDB's bundled CALL dbgen.

If neither source flag is given, DUCKDB_BIN and then this checkout's release or
debug binary are tried. Docker is used only with --local-container. The image
comes from PGPLAN_CONTAINER_IMAGE and remains running for make_plan.sh.

Environment overrides:
  Defaults are sourced from auto_test/configs.sh. PG_DSN, PSQL_BIN,
  DUCKDB_BIN, and TPCH_DATA_DIR remain overridable.
  PGPLAN_CONTAINER_{NAME,PORT,DATABASE,USER,PASSWORD}

--force drops only the eight public TPC-H tables; it never drops the database
or schema. Use a dedicated plan-generation database.
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
            [ "$LOCAL_CONTAINER" -eq 0 ] || die "use either --pg-dsn or --local-container, not both"
            PG_DSN="$2"
            PG_DSN_EXPLICIT=1
            shift 2
            ;;
        --data-dir)
            [ $# -ge 2 ] || die "$1 requires a value"
            [ "$SOURCE_ARG" != "duckdb" ] || die "use only one of --data-dir and --duckdb-bin"
            SOURCE_ARG="data"
            DATA_DIR="$2"
            DUCKDB_BIN=""
            shift 2
            ;;
        --duckdb-bin)
            [ $# -ge 2 ] || die "$1 requires a value"
            [ "$SOURCE_ARG" != "data" ] || die "use only one of --data-dir and --duckdb-bin"
            SOURCE_ARG="duckdb"
            DUCKDB_BIN="$2"
            DATA_DIR=""
            shift 2
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --local-container)
            [ "$PG_DSN_EXPLICIT" -eq 0 ] || die "use either --pg-dsn or --local-container, not both"
            LOCAL_CONTAINER=1
            PG_DSN=""
            if [ "$PSQL_BIN_WAS_SET" != "x" ]; then
                PSQL_BIN="$SCRIPT_DIR/docker_psql.sh"
            fi
            shift
            ;;
        --container-name)
            [ $# -ge 2 ] || die "$1 requires a value"
            CONTAINER_NAME="$2"
            shift 2
            ;;
        --port)
            [ $# -ge 2 ] || die "$1 requires a value"
            CONTAINER_PORT="$2"
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

if [ -n "$DATA_DIR" ] && [ -n "$DUCKDB_BIN" ]; then
    die "use only one of --data-dir and --duckdb-bin"
fi
# docker_psql.sh is a separate process and reads these values from configs.sh.
# Export the resolved CLI overrides so it addresses the container just started
# by this invocation rather than the configured defaults.
if [ "$LOCAL_CONTAINER" -eq 1 ]; then
    export PGPLAN_CONTAINER_NAME="$CONTAINER_NAME"
    export PGPLAN_CONTAINER_PORT="$CONTAINER_PORT"
    export PGPLAN_CONTAINER_DATABASE="$CONTAINER_DATABASE"
    export PGPLAN_CONTAINER_USER="$CONTAINER_USER"
    export PGPLAN_CONTAINER_PASSWORD="$CONTAINER_PASSWORD"
fi
[[ "$CONTAINER_PORT" =~ ^[0-9]+$ ]] || die "--port must be numeric"
[ "$CONTAINER_PORT" -ge 1 ] && [ "$CONTAINER_PORT" -le 65535 ] || \
    die "--port must be between 1 and 65535"

TEMP_ROOT=""
cleanup() {
    local rc=$?
    if [ "${CONTAINER_STARTED:-0}" -eq 1 ] && [ "${KEEP_CONTAINER:-0}" -eq 0 ]; then
        docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
    if [ -n "${TEMP_ROOT:-}" ] && [ -d "$TEMP_ROOT" ]; then
        rm -rf -- "$TEMP_ROOT"
    fi
    return "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

validate_data_files() {
    local table
    for table in "${TABLES[@]}"; do
        if [ -f "$DATA_DIR/$table.tbl" ] || [ -f "$DATA_DIR/$table.csv" ]; then
            :
        else
            die "missing $table.tbl or $table.csv in $DATA_DIR"
        fi
    done
}

if [[ "$PSQL_BIN" == */* ]]; then
    [ -x "$PSQL_BIN" ] || die "PSQL_BIN is not executable: $PSQL_BIN"
else
    command -v "$PSQL_BIN" >/dev/null 2>&1 || die "psql not found: $PSQL_BIN"
fi
if [ "$LOCAL_CONTAINER" -eq 1 ]; then
    command -v docker >/dev/null 2>&1 || die "docker is required for --local-container"
else
    [ -n "$PG_DSN" ] || die "--pg-dsn is required (or use --local-container)"
fi

if [ -z "$DATA_DIR" ] && [ -z "$DUCKDB_BIN" ]; then
    if [ -x "$REPO_ROOT/build/release/duckdb" ]; then
        DUCKDB_BIN="$REPO_ROOT/build/release/duckdb"
    elif [ -x "$REPO_ROOT/build/debug/duckdb" ]; then
        DUCKDB_BIN="$REPO_ROOT/build/debug/duckdb"
    fi
fi
if [ -n "$DATA_DIR" ]; then
    [ -d "$DATA_DIR" ] || die "TPC-H data directory does not exist: $DATA_DIR"
    validate_data_files
else
    [ -n "$DUCKDB_BIN" ] || \
        die "no data source: pass --data-dir or --duckdb-bin (or set DUCKDB_BIN)"
    [ -x "$DUCKDB_BIN" ] || die "DuckDB binary is not executable: $DUCKDB_BIN"
fi

if [ -z "$DATA_DIR" ]; then
    TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/duckyan-tpch-pg.XXXXXX")"
    DATA_DIR="$TEMP_ROOT/data"
    mkdir -p "$DATA_DIR"
    GENERATOR_DB="$TEMP_ROOT/tpch_sf001.duckdb"
    echo "[PGPLAN] generating TPC-H SF0.01 with $DUCKDB_BIN"
    "$DUCKDB_BIN" "$GENERATOR_DB" -c "CALL dbgen(sf=0.01);" >/dev/null
    for table in "${TABLES[@]}"; do
        file="$DATA_DIR/$table.csv"
        escaped_file="$(printf '%s' "$file" | sed "s/'/''/g")"
        "$DUCKDB_BIN" "$GENERATOR_DB" -c \
            "COPY $table TO '$escaped_file' (FORMAT CSV, DELIMITER '|', HEADER FALSE);" \
            >/dev/null
    done
    validate_data_files
fi

if [ "$LOCAL_CONTAINER" -eq 1 ]; then
    if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
        die "container already exists: $CONTAINER_NAME"
    fi
    echo "[PGPLAN] starting $CONTAINER_IMAGE container $CONTAINER_NAME"
    POSTGRES_PASSWORD="$CONTAINER_PASSWORD" docker run --detach --rm \
        --name "$CONTAINER_NAME" \
        --env "POSTGRES_DB=$CONTAINER_DATABASE" \
        --env "POSTGRES_USER=$CONTAINER_USER" \
        --env POSTGRES_PASSWORD \
        --publish "127.0.0.1:$CONTAINER_PORT:5432" \
        "$CONTAINER_IMAGE" >/dev/null
    CONTAINER_STARTED=1

    READY=0
    for _ in $(seq 1 60); do
        if docker exec "$CONTAINER_NAME" pg_isready \
            --host=127.0.0.1 --port=5432 \
            --username "$CONTAINER_USER" --dbname "$CONTAINER_DATABASE" >/dev/null 2>&1; then
            READY=1
            break
        fi
        sleep 1
    done
    [ "$READY" -eq 1 ] || die "PostgreSQL container did not become ready"
    export PGPASSWORD="$CONTAINER_PASSWORD"
    PG_DSN="host=127.0.0.1 port=$CONTAINER_PORT user=$CONTAINER_USER dbname=$CONTAINER_DATABASE"
fi

[ -n "$PG_DSN" ] || die "--pg-dsn is required (or use --local-container)"

ACTUAL_VERSION="$({
    "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
        --command="SELECT current_setting('server_version_num');"
} | tr -d '[:space:]')"
[ "$ACTUAL_VERSION" = "$EXPECTED_PG_VERSION" ] || \
    die "PostgreSQL server_version_num must be $EXPECTED_PG_VERSION, got ${ACTUAL_VERSION:-<empty>}"

validate_data_files

EXISTING_TABLES="$({
    "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --command="
        SELECT ((to_regclass('public.region') IS NOT NULL)::int +
                (to_regclass('public.nation') IS NOT NULL)::int +
                (to_regclass('public.supplier') IS NOT NULL)::int +
                (to_regclass('public.customer') IS NOT NULL)::int +
                (to_regclass('public.part') IS NOT NULL)::int +
                (to_regclass('public.partsupp') IS NOT NULL)::int +
                (to_regclass('public.orders') IS NOT NULL)::int +
                (to_regclass('public.lineitem') IS NOT NULL)::int);"
} | tr -d '[:space:]')"
if [ "${EXISTING_TABLES:-0}" -ne 0 ] && [ "$FORCE" -ne 1 ]; then
    die "$EXISTING_TABLES TPC-H table(s) already exist; pass --force to replace them"
fi

if [ "$FORCE" -eq 1 ]; then
    "$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --command="
        DROP TABLE IF EXISTS public.lineitem, public.orders, public.partsupp,
            public.part, public.customer, public.supplier, public.nation,
            public.region;"
fi

"$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
    --file="$SCRIPT_DIR/tpch_schema.sql"

echo "[PGPLAN] loading TPC-H SF0.01"
for table in "${TABLES[@]}"; do
    if [ -f "$DATA_DIR/$table.tbl" ]; then
        # Official dbgen .tbl files end each row with an extra delimiter.
        sed 's/|$//' "$DATA_DIR/$table.tbl" | \
            "$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
                --command="\copy public.$table FROM STDIN WITH (FORMAT text, DELIMITER '|', NULL '')"
    else
        "$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
            --command="\copy public.$table FROM STDIN WITH (FORMAT csv, DELIMITER '|', NULL '')" \
            < "$DATA_DIR/$table.csv"
    fi
done

CARDINALITIES="$({
    "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --command="
        SELECT (SELECT count(*) FROM public.region),
               (SELECT count(*) FROM public.nation),
               (SELECT count(*) FROM public.supplier),
               (SELECT count(*) FROM public.customer),
               (SELECT count(*) FROM public.part),
               (SELECT count(*) FROM public.partsupp),
               (SELECT count(*) FROM public.orders),
               (SELECT count(*) FROM public.lineitem);"
} | tr -d '[:space:]')"
EXPECTED_CARDINALITIES="5|25|100|1500|2000|8000|15000|60175"
[ "$CARDINALITIES" = "$EXPECTED_CARDINALITIES" ] || \
    die "TPC-H cardinalities are not SF0.01: expected $EXPECTED_CARDINALITIES, got $CARDINALITIES"

"$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --command="ANALYZE;"

ROW_COUNTS="$({
    "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --command="
        SELECT 'part=' || (SELECT count(*) FROM public.part) ||
               ' supplier=' || (SELECT count(*) FROM public.supplier) ||
               ' partsupp=' || (SELECT count(*) FROM public.partsupp) ||
               ' lineitem=' || (SELECT count(*) FROM public.lineitem);"
})"
echo "[PGPLAN] ready: PostgreSQL=$ACTUAL_VERSION data=tpch-sf0.01 $ROW_COUNTS"
if [ "$LOCAL_CONTAINER" -eq 1 ]; then
    KEEP_CONTAINER=1
    echo "[PGPLAN] container remains running: $CONTAINER_NAME"
    echo "[PGPLAN] PG_DSN='host=127.0.0.1 port=$CONTAINER_PORT" \
        "user=$CONTAINER_USER dbname=$CONTAINER_DATABASE'"
    echo "[PGPLAN] export PGPASSWORD to the configured container password before make_plan.sh"
fi
