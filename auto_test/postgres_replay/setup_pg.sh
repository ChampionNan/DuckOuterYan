#!/usr/bin/env bash
# Ensure the pinned PostgreSQL planner and its SF0.01 TPC-H database are ready.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../configs.sh
source "$SCRIPT_DIR/../configs.sh"

EXPECTED_CARDINALITIES="5|25|100|1500|2000|8000|15000|60175"
SKIP_DATA="${SKIP_PG_DATA:-0}"
FORCE_EXTERNAL_DATA="${PGPLAN_FORCE_DATA:-0}"
DOWNLOAD_PART=""
INITDB_PASSWORD_FILE=""
AUTH_SQL_FILE=""
HBA_TEMP_FILE=""

usage() {
    cat <<'USAGE'
Usage: setup_pg.sh [--skip-data] [--force-external-data]

All defaults come from auto_test/configs.sh. PGPLAN_SETUP selects one of:
  source    Default: download/build/install PostgreSQL 16.2 if absent, then
            initialize/start the repo-local managed server.
  docker    Optional: start/reuse PGPLAN_CONTAINER_NAME with the pinned image.
  external  Validate the caller-supplied PG_DSN and PSQL_BIN without starting it.

The script always verifies the exact TPC-H SF0.01 cardinalities and refreshes
planner statistics. --skip-data (or SKIP_PG_DATA=1) forbids loading/repair and
fails when that verified data is absent. Managed source/docker databases are
otherwise repaired after a partial load. External databases are never replaced
unless --force-external-data (or PGPLAN_FORCE_DATA=1) is explicit.
USAGE
}

die() {
    echo "ERROR: $*" >&2
    exit 2
}

cleanup() {
    local rc=$?
    if [ -n "${DOWNLOAD_PART:-}" ] && [ -f "$DOWNLOAD_PART" ]; then
        rm -f -- "$DOWNLOAD_PART"
    fi
    if [ -n "${INITDB_PASSWORD_FILE:-}" ] && [ -f "$INITDB_PASSWORD_FILE" ]; then
        rm -f -- "$INITDB_PASSWORD_FILE"
    fi
    if [ -n "${AUTH_SQL_FILE:-}" ] && [ -f "$AUTH_SQL_FILE" ]; then
        rm -f -- "$AUTH_SQL_FILE"
    fi
    if [ -n "${HBA_TEMP_FILE:-}" ] && [ -f "$HBA_TEMP_FILE" ]; then
        rm -f -- "$HBA_TEMP_FILE"
    fi
    return "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while [ $# -gt 0 ]; do
    case "$1" in
        --skip-data)
            SKIP_DATA=1
            shift
            ;;
        --force-external-data)
            FORCE_EXTERNAL_DATA=1
            shift
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

case "$SKIP_DATA" in 0|1) ;; *) die "SKIP_PG_DATA must be 0 or 1" ;; esac
case "$FORCE_EXTERNAL_DATA" in 0|1) ;; *) die "PGPLAN_FORCE_DATA must be 0 or 1" ;; esac
case "$PGPLAN_SETUP" in source|docker|external) ;; *)
    die "PGPLAN_SETUP must be source, docker, or external"
esac
if [ "$PGPLAN_SETUP" = "source" ]; then
    case "$PGPLAN_HOST" in
        127.0.0.1|::1|localhost) ;;
        *)
            die "managed source mode requires a loopback PGPLAN_HOST (127.0.0.1, ::1, or localhost)"
            ;;
    esac
    [ -n "$PGPLAN_PASSWORD" ] || \
        die "managed source mode requires a nonempty PGPLAN_PASSWORD"
    case "$PGPLAN_PASSWORD" in
        *$'\n'*|*$'\r'*)
            die "PGPLAN_PASSWORD must not contain a newline in managed source mode"
            ;;
    esac
fi
[ "$PGPLAN_VERSION" = "16.2" ] || die "PGPlan v1 requires PGPLAN_VERSION=16.2"
[ "$PGPLAN_VERSION_NUM" = "160002" ] || \
    die "PGPlan v1 requires PGPLAN_VERSION_NUM=160002"
[[ "$PGPLAN_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]] || \
    die "PGPLAN_SOURCE_SHA256 must be 64 lowercase hexadecimal characters"
[[ "$PGPLAN_PORT" =~ ^[0-9]+$ ]] || die "PGPLAN_PORT must be numeric"
[ "$PGPLAN_PORT" -ge 1 ] && [ "$PGPLAN_PORT" -le 65535 ] || \
    die "PGPLAN_PORT must be between 1 and 65535"
[[ "$PGPLAN_BUILD_JOBS" =~ ^[1-9][0-9]*$ ]] || \
    die "PGPLAN_BUILD_JOBS must be a positive integer"
[[ "$PGPLAN_DATABASE" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || \
    die "PGPLAN_DATABASE must be an unquoted PostgreSQL identifier"
[[ "$PGPLAN_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || \
    die "PGPLAN_USER must be an unquoted PostgreSQL identifier"
MANAGED_DSN="host=$PGPLAN_HOST port=$PGPLAN_PORT dbname=$PGPLAN_DATABASE user=$PGPLAN_USER"
if [ "$PGPLAN_SETUP" != "external" ] && [ "$PG_DSN" != "$MANAGED_DSN" ]; then
    die "managed source/docker mode requires the configs.sh-derived PG_DSN; set PGPLAN_HOST/PORT/DATABASE/USER, or use PGPLAN_SETUP=external"
fi
if [ "$PGPLAN_SETUP" = "docker" ]; then
    [ -n "$PGPLAN_CONTAINER_NAME" ] || die "PGPLAN_CONTAINER_NAME must not be empty"
    [ "$PGPLAN_CONTAINER_PORT" = "$PGPLAN_PORT" ] || \
        die "PGPLAN_CONTAINER_PORT and PGPLAN_PORT must match in Docker mode"
    [ "$PGPLAN_CONTAINER_DATABASE" = "$PGPLAN_DATABASE" ] || \
        die "PGPLAN_CONTAINER_DATABASE and PGPLAN_DATABASE must match in Docker mode"
    [ "$PGPLAN_CONTAINER_USER" = "$PGPLAN_USER" ] || \
        die "PGPLAN_CONTAINER_USER and PGPLAN_USER must match in Docker mode"
    if [ "$PSQL_BIN" != "$OY_REPO_ROOT/auto_test/pgplan/docker_psql.sh" ] && \
            [ "$PSQL_BIN" != "$SCRIPT_DIR/docker_psql.sh" ]; then
        die "managed Docker mode requires PSQL_BIN=$OY_REPO_ROOT/auto_test/pgplan/docker_psql.sh"
    fi
fi

require_executable() {
    local executable="$1" label="$2"
    if [[ "$executable" == */* ]]; then
        [ -x "$executable" ] || die "$label is not executable: $executable"
    else
        command -v "$executable" >/dev/null 2>&1 || die "$label not found: $executable"
    fi
}

sha256_file() {
    local path="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$path" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$path" | awk '{print $1}'
    else
        die "sha256sum or shasum is required to verify PostgreSQL source"
    fi
}

ensure_source_build() {
    local archive source_tree actual_hash actual_version url compat_source compat_patch
    archive="$PGPLAN_SOURCE_DIR/postgresql-$PGPLAN_VERSION.tar.gz"
    source_tree="$PGPLAN_SOURCE_DIR/postgresql-$PGPLAN_VERSION"
    url="https://ftp.postgresql.org/pub/source/v$PGPLAN_VERSION/postgresql-$PGPLAN_VERSION.tar.gz"

    if [ -x "$PGPLAN_INSTALL_DIR/bin/postgres" ]; then
        actual_version="$({ "$PGPLAN_INSTALL_DIR/bin/postgres" --version; } | awk '{print $3}')"
        [ "$actual_version" = "$PGPLAN_VERSION" ] || \
            die "installed PostgreSQL is $actual_version, expected $PGPLAN_VERSION: $PGPLAN_INSTALL_DIR"
        return
    fi

    [ "$(id -u)" -ne 0 ] || \
        die "PostgreSQL source mode cannot run as root; use PGPLAN_SETUP=docker"
    require_executable make make
    require_executable patch patch
    require_executable tar tar
    mkdir -p "$PGPLAN_SOURCE_DIR"

    if [ ! -f "$archive" ]; then
        DOWNLOAD_PART="$archive.part.$$"
        echo "[PGPLAN] downloading PostgreSQL $PGPLAN_VERSION"
        if command -v curl >/dev/null 2>&1; then
            curl --fail --location --retry 3 --output "$DOWNLOAD_PART" "$url"
        elif command -v wget >/dev/null 2>&1; then
            wget --output-document="$DOWNLOAD_PART" "$url"
        else
            die "curl or wget is required to download PostgreSQL source"
        fi
        actual_hash="$(sha256_file "$DOWNLOAD_PART")"
        [ "$actual_hash" = "$PGPLAN_SOURCE_SHA256" ] || \
            die "PostgreSQL source SHA-256 mismatch: expected $PGPLAN_SOURCE_SHA256, got $actual_hash"
        mv -- "$DOWNLOAD_PART" "$archive"
        DOWNLOAD_PART=""
    fi

    actual_hash="$(sha256_file "$archive")"
    [ "$actual_hash" = "$PGPLAN_SOURCE_SHA256" ] || \
        die "cached PostgreSQL source SHA-256 mismatch: $archive"
    if [ ! -d "$source_tree" ]; then
        echo "[PGPLAN] extracting $archive"
        tar -xzf "$archive" -C "$PGPLAN_SOURCE_DIR"
    fi
    [ -x "$source_tree/configure" ] || die "PostgreSQL source tree is incomplete: $source_tree"

    # PostgreSQL 16.2 predates the macOS SDK that added strchrnul. Force its
    # portable fallback and give that local helper a private name, avoiding a
    # declaration collision with newer SDK headers. This touches only frontend
    # snprintf compatibility code, not the server planner or optimizer.
    compat_source="$source_tree/src/port/snprintf.c"
    compat_patch="$SCRIPT_DIR/postgresql-16.2-strchrnul.patch"
    if ! grep -q 'SNPRINTF_STRCHRNUL' "$compat_source"; then
        patch --directory="$source_tree" --strip=1 --forward < "$compat_patch"
    fi
    grep -q 'SNPRINTF_STRCHRNUL' "$compat_source" || \
        die "failed to apply PostgreSQL 16.2 strchrnul compatibility patch"

    echo "[PGPLAN] configuring PostgreSQL $PGPLAN_VERSION in $PGPLAN_INSTALL_DIR"
    (
        cd "$source_tree"
        # The PGPlan database needs the core server and psql only. Avoid
        # optional ICU/readline/zlib build dependencies so the same pinned
        # planner can be built on a minimal experiment server.
        ac_cv_func_strchrnul=no ./configure "--prefix=$PGPLAN_INSTALL_DIR" \
            --without-icu --without-readline --without-zlib
        make -j"$PGPLAN_BUILD_JOBS"
        make install
    )
    [ -x "$PGPLAN_INSTALL_DIR/bin/postgres" ] || \
        die "PostgreSQL installation did not produce $PGPLAN_INSTALL_DIR/bin/postgres"
}

ensure_source_server() {
    local data_major expected_major admin_dsn database_exists actual_version
    local configured_data_dir server_data_dir
    [ "$(id -u)" -ne 0 ] || \
        die "PostgreSQL source mode cannot run as root; use PGPLAN_SETUP=docker"
    [[ "$PGPLAN_HOST" =~ ^[A-Za-z0-9_.:-]+$ ]] || \
        die "PGPLAN_HOST contains unsupported characters: $PGPLAN_HOST"
    require_executable "$PGPLAN_INSTALL_DIR/bin/initdb" initdb
    require_executable "$PGPLAN_INSTALL_DIR/bin/pg_ctl" pg_ctl
    require_executable "$PGPLAN_INSTALL_DIR/bin/createdb" createdb

    if [ ! -f "$PGPLAN_DATA_DIR/PG_VERSION" ]; then
        if [ -d "$PGPLAN_DATA_DIR" ] && \
                [ -n "$(find "$PGPLAN_DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
            die "PGPLAN_DATA_DIR is nonempty but is not a PostgreSQL cluster: $PGPLAN_DATA_DIR"
        fi
        mkdir -p "$PGPLAN_DATA_DIR"
        echo "[PGPLAN] initializing $PGPLAN_DATA_DIR"
        umask 077
        INITDB_PASSWORD_FILE="$(mktemp "$PGPLAN_INSTALL_DIR/.pgplan-initdb-password.XXXXXX")"
        printf '%s\n' "$PGPLAN_PASSWORD" > "$INITDB_PASSWORD_FILE"
        "$PGPLAN_INSTALL_DIR/bin/initdb" -D "$PGPLAN_DATA_DIR" \
            -E UTF8 --locale=C -U "$PGPLAN_USER" \
            --auth-local=peer --auth-host=scram-sha-256 \
            --pwfile="$INITDB_PASSWORD_FILE"
        rm -f -- "$INITDB_PASSWORD_FILE"
        INITDB_PASSWORD_FILE=""
    fi

    data_major="$(tr -d '[:space:]' < "$PGPLAN_DATA_DIR/PG_VERSION")"
    expected_major="${PGPLAN_VERSION%%.*}"
    [ "$data_major" = "$expected_major" ] || \
        die "PostgreSQL data directory is version $data_major, expected $expected_major"

    if ! "$PGPLAN_INSTALL_DIR/bin/pg_ctl" -D "$PGPLAN_DATA_DIR" status >/dev/null 2>&1; then
        mkdir -p "$(dirname "$PGPLAN_LOG_FILE")"
        echo "[PGPLAN] starting PostgreSQL on $PGPLAN_HOST:$PGPLAN_PORT"
        "$PGPLAN_INSTALL_DIR/bin/pg_ctl" -D "$PGPLAN_DATA_DIR" \
            -l "$PGPLAN_LOG_FILE" -w -t 60 \
            -o "-h $PGPLAN_HOST -p $PGPLAN_PORT" start
    fi

    require_executable "$PSQL_BIN" psql
    admin_dsn="host=$PGPLAN_HOST port=$PGPLAN_PORT dbname=postgres user=$PGPLAN_USER"
    actual_version="$({
        "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$admin_dsn" \
            --command="SELECT current_setting('server_version_num');"
    } | tr -d '[:space:]')"
    [ "$actual_version" = "$PGPLAN_VERSION_NUM" ] || \
        die "configured source endpoint is PostgreSQL $actual_version, expected $PGPLAN_VERSION_NUM"
    server_data_dir="$({
        "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$admin_dsn" \
            --command="SELECT current_setting('data_directory');"
    })"
    [ -d "$server_data_dir" ] || \
        die "configured source endpoint reported an invalid data_directory: $server_data_dir"
    configured_data_dir="$(cd "$PGPLAN_DATA_DIR" && pwd -P)"
    server_data_dir="$(cd "$server_data_dir" && pwd -P)"
    [ "$server_data_dir" = "$configured_data_dir" ] || \
        die "configured source endpoint belongs to $server_data_dir, not $configured_data_dir"

    secure_source_authentication "$admin_dsn"

    database_exists="$({
        "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$admin_dsn" \
            --command="SELECT 1 FROM pg_database WHERE datname = '$PGPLAN_DATABASE';"
    } | tr -d '[:space:]')"
    if [ "$database_exists" != "1" ]; then
        echo "[PGPLAN] creating database $PGPLAN_DATABASE"
        "$PGPLAN_INSTALL_DIR/bin/createdb" --host="$PGPLAN_HOST" \
            --port="$PGPLAN_PORT" --username="$PGPLAN_USER" \
            "$PGPLAN_DATABASE"
    fi
}

active_hba_uses_trust() {
    local hba_file="$1"
    awk '
        /^[[:space:]]*($|#)/ { next }
        $1 == "local" && $4 == "trust" { found = 1 }
        $1 ~ /^host/ && $5 == "trust" { found = 1 }
        END { exit(found ? 0 : 1) }
    ' "$hba_file"
}

secure_source_authentication() {
    local admin_dsn="$1" hba_file escaped_password auth_rule_errors
    hba_file="$PGPLAN_DATA_DIR/pg_hba.conf"
    [ -f "$hba_file" ] || die "managed source cluster has no pg_hba.conf: $hba_file"

    # Set the managed role password before replacing trust rules. The SQL lives
    # only in a mode-600 file so the password never appears in argv or logs.
    escaped_password="${PGPLAN_PASSWORD//\'/\'\'}"
    umask 077
    AUTH_SQL_FILE="$(mktemp "$PGPLAN_DATA_DIR/.pgplan-role-password.XXXXXX")"
    {
        printf 'SET standard_conforming_strings = on;\n'
        printf 'ALTER ROLE "%s" PASSWORD '\''%s'\'';\n' "$PGPLAN_USER" "$escaped_password"
    } > "$AUTH_SQL_FILE"
    "$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$admin_dsn" \
        --file="$AUTH_SQL_FILE" >/dev/null
    rm -f -- "$AUTH_SQL_FILE"
    AUTH_SQL_FILE=""

    if active_hba_uses_trust "$hba_file"; then
        HBA_TEMP_FILE="$(mktemp "$PGPLAN_DATA_DIR/.pg_hba.pgplan.XXXXXX")"
        awk '
            BEGIN { OFS = "\t" }
            /^[[:space:]]*($|#)/ { print; next }
            $1 == "local" && $4 == "trust" { $4 = "peer" }
            $1 ~ /^host/ && $5 == "trust" { $5 = "scram-sha-256" }
            { print }
        ' "$hba_file" > "$HBA_TEMP_FILE"
        chmod 600 "$HBA_TEMP_FILE"
        if active_hba_uses_trust "$HBA_TEMP_FILE"; then
            die "failed to remove trust authentication from managed pg_hba.conf"
        fi
        mv -- "$HBA_TEMP_FILE" "$hba_file"
        HBA_TEMP_FILE=""
        "$PGPLAN_INSTALL_DIR/bin/pg_ctl" -D "$PGPLAN_DATA_DIR" reload >/dev/null
    fi

    auth_rule_errors="$({
        "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$admin_dsn" \
            --command="SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL OR auth_method = 'trust';"
    } | tr -d '[:space:]')"
    [ "$auth_rule_errors" = "0" ] || \
        die "managed pg_hba.conf still has invalid or trust-authentication rules"

    # A fresh host connection with a deliberately wrong password must fail;
    # otherwise a stale in-memory trust rule could still expose the cluster.
    if PGPASSWORD="${PGPLAN_PASSWORD}.pgplan-invalid-probe" \
            "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$admin_dsn" \
            --command="SELECT 1;" >/dev/null 2>&1; then
        die "managed PostgreSQL host authentication still accepts an invalid password"
    fi
    "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$admin_dsn" \
        --command="SELECT 1;" >/dev/null
}

ensure_docker_server() {
    local running ready
    require_executable docker docker
    if docker inspect "$PGPLAN_CONTAINER_NAME" >/dev/null 2>&1; then
        running="$(docker inspect --format '{{.State.Running}}' "$PGPLAN_CONTAINER_NAME")"
        if [ "$running" != "true" ]; then
            echo "[PGPLAN] starting existing container $PGPLAN_CONTAINER_NAME"
            docker start "$PGPLAN_CONTAINER_NAME" >/dev/null
        fi
    else
        echo "[PGPLAN] starting $PGPLAN_CONTAINER_IMAGE container $PGPLAN_CONTAINER_NAME"
        POSTGRES_PASSWORD="$PGPLAN_CONTAINER_PASSWORD" docker run --detach \
            --name "$PGPLAN_CONTAINER_NAME" \
            --env "POSTGRES_DB=$PGPLAN_CONTAINER_DATABASE" \
            --env "POSTGRES_USER=$PGPLAN_CONTAINER_USER" \
            --env POSTGRES_PASSWORD \
            --publish "127.0.0.1:$PGPLAN_CONTAINER_PORT:5432" \
            "$PGPLAN_CONTAINER_IMAGE" >/dev/null
    fi

    ready=0
    for _ in $(seq 1 60); do
        if docker exec "$PGPLAN_CONTAINER_NAME" pg_isready \
                --host=127.0.0.1 --port=5432 \
                --username "$PGPLAN_CONTAINER_USER" \
                --dbname "$PGPLAN_CONTAINER_DATABASE" >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 1
    done
    [ "$ready" -eq 1 ] || die "PostgreSQL container did not become ready"

    if ! PGPASSWORD="$PGPLAN_CONTAINER_PASSWORD" docker exec --env PGPASSWORD \
            "$PGPLAN_CONTAINER_NAME" psql -X -qAt --set=ON_ERROR_STOP=1 \
            --host=127.0.0.1 --port=5432 \
            --username="$PGPLAN_CONTAINER_USER" --dbname="$PGPLAN_CONTAINER_DATABASE" \
            --command="SELECT 1;" >/dev/null 2>&1; then
        die "managed PostgreSQL container rejected the configured private password; explicitly remove/recreate $PGPLAN_CONTAINER_NAME or provide its current PGPLAN_CONTAINER_PASSWORD"
    fi
    if PGPASSWORD="${PGPLAN_CONTAINER_PASSWORD}.pgplan-invalid-probe" \
            docker exec --env PGPASSWORD "$PGPLAN_CONTAINER_NAME" \
            psql -X -qAt --set=ON_ERROR_STOP=1 \
            --host=127.0.0.1 --port=5432 \
            --username="$PGPLAN_CONTAINER_USER" --dbname="$PGPLAN_CONTAINER_DATABASE" \
            --command="SELECT 1;" >/dev/null 2>&1; then
        die "managed PostgreSQL container host authentication accepts an invalid password"
    fi
    require_executable "$PSQL_BIN" psql
}

server_version_num() {
    {
        "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
            --command="SELECT current_setting('server_version_num');"
    } | tr -d '[:space:]'
}

existing_table_count() {
    {
        "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --command="
            SELECT ((to_regclass('public.region') IS NOT NULL)::int +
                    (to_regclass('public.nation') IS NOT NULL)::int +
                    (to_regclass('public.supplier') IS NOT NULL)::int +
                    (to_regclass('public.customer') IS NOT NULL)::int +
                    (to_regclass('public.part') IS NOT NULL)::int +
                    (to_regclass('public.partsupp') IS NOT NULL)::int +
                    (to_regclass('public.orders') IS NOT NULL)::int +
                    (to_regclass('public.lineitem') IS NOT NULL)::int);"
    } | tr -d '[:space:]'
}

loaded_cardinalities() {
    {
        "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --command="
            SELECT (SELECT count(*) FROM public.region),
                   (SELECT count(*) FROM public.nation),
                   (SELECT count(*) FROM public.supplier),
                   (SELECT count(*) FROM public.customer),
                   (SELECT count(*) FROM public.part),
                   (SELECT count(*) FROM public.partsupp),
                   (SELECT count(*) FROM public.orders),
                   (SELECT count(*) FROM public.lineitem);"
    } | tr -d '[:space:]'
}

analyze_plan_tables() {
    "$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --command="
        ANALYZE public.region, public.nation, public.supplier, public.customer,
                public.part, public.partsupp, public.orders, public.lineitem;"
}

case "$PGPLAN_SETUP" in
    source)
        ensure_source_build
        ensure_source_server
        ;;
    docker)
        ensure_docker_server
        ;;
    external)
        [ -n "$PG_DSN" ] || die "PG_DSN is required for PGPLAN_SETUP=external"
        require_executable "$PSQL_BIN" psql
        ;;
esac

ACTUAL_VERSION="$(server_version_num)"
[ "$ACTUAL_VERSION" = "$PGPLAN_VERSION_NUM" ] || \
    die "PostgreSQL server_version_num mismatch: expected $PGPLAN_VERSION_NUM, got ${ACTUAL_VERSION:-<empty>}"

TABLE_COUNT="$(existing_table_count)"
case "$TABLE_COUNT" in ''|*[!0-9]*) die "could not inspect PostgreSQL TPC-H tables" ;; esac
CARDINALITIES=""
if [ "$TABLE_COUNT" -eq 8 ]; then
    CARDINALITIES="$(loaded_cardinalities)"
fi

if [ "$CARDINALITIES" = "$EXPECTED_CARDINALITIES" ]; then
    echo "[PGPLAN] reusing verified TPC-H SF0.01 data"
else
    if [ "$SKIP_DATA" -eq 1 ]; then
        die "SKIP_PG_DATA=1 requires existing TPC-H SF0.01 data; found $TABLE_COUNT table(s), cardinalities=${CARDINALITIES:-<unavailable>}"
    fi
    if [ "$SKIP_DATA" -eq 0 ]; then
        PREPARE_ARGS=(--pg-dsn "$PG_DSN")
        if [ -n "${TPCH_DATA_DIR:-}" ]; then
            PREPARE_ARGS+=(--data-dir "$TPCH_DATA_DIR")
        else
            PREPARE_ARGS+=(--duckdb-bin "$DUCKDB_BIN")
        fi
        if [ "$PGPLAN_SETUP" != "external" ] || [ "$FORCE_EXTERNAL_DATA" -eq 1 ]; then
            PREPARE_ARGS+=(--force)
        elif [ "$TABLE_COUNT" -ne 0 ]; then
            die "external database has incomplete/non-SF0.01 TPC-H data; set PGPLAN_FORCE_DATA=1 to replace only those eight tables"
        fi
        bash "$SCRIPT_DIR/prepare_tpch_pg.sh" "${PREPARE_ARGS[@]}"

        TABLE_COUNT="$(existing_table_count)"
        [ "$TABLE_COUNT" -eq 8 ] || die "TPC-H preparation left only $TABLE_COUNT of 8 tables"
        CARDINALITIES="$(loaded_cardinalities)"
        [ "$CARDINALITIES" = "$EXPECTED_CARDINALITIES" ] || \
            die "TPC-H cardinalities are not SF0.01 after preparation: $CARDINALITIES"
    fi
fi

echo "[PGPLAN] refreshing PostgreSQL planner statistics"
analyze_plan_tables

echo "[PGPLAN] setup ready: mode=$PGPLAN_SETUP PostgreSQL=$ACTUAL_VERSION"
if [ "$PGPLAN_SETUP" = "external" ]; then
    echo "[PGPLAN] external PG_DSN validated (redacted); PSQL_BIN='$PSQL_BIN'"
else
    echo "[PGPLAN] endpoint=$PGPLAN_HOST:$PGPLAN_PORT/$PGPLAN_DATABASE PSQL_BIN='$PSQL_BIN'"
fi
