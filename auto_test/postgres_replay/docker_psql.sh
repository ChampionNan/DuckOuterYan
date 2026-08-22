#!/usr/bin/env bash
# Present the PostgreSQL client's CLI while executing it inside the managed
# container. This keeps PGPLAN_SETUP=docker independent of a host psql.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../configs.sh
source "$SCRIPT_DIR/../configs.sh"

die() {
    echo "ERROR: $*" >&2
    exit 2
}

command -v docker >/dev/null 2>&1 || die "docker is required for PGPLAN_SETUP=docker"
docker inspect "$PGPLAN_CONTAINER_NAME" >/dev/null 2>&1 || \
    die "PostgreSQL container is not available: $PGPLAN_CONTAINER_NAME"

INTERNAL_DSN="host=/var/run/postgresql port=5432 dbname=$PGPLAN_CONTAINER_DATABASE user=$PGPLAN_CONTAINER_USER"
STDIN_FILE=""
PSQL_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --dbname=*)
            PSQL_ARGS+=("--dbname=$INTERNAL_DSN")
            shift
            ;;
        --dbname|-d)
            [ $# -ge 2 ] || die "$1 requires a value"
            PSQL_ARGS+=("--dbname=$INTERNAL_DSN")
            shift 2
            ;;
        --file=*)
            STDIN_FILE="${1#--file=}"
            PSQL_ARGS+=("--file=-")
            shift
            ;;
        --file|-f)
            [ $# -ge 2 ] || die "$1 requires a value"
            STDIN_FILE="$2"
            PSQL_ARGS+=("--file=-")
            shift 2
            ;;
        *)
            PSQL_ARGS+=("$1")
            shift
            ;;
    esac
done

if [ -n "$STDIN_FILE" ]; then
    [ -r "$STDIN_FILE" ] || die "psql input file is not readable: $STDIN_FILE"
    PGPASSWORD="$PGPLAN_CONTAINER_PASSWORD" docker exec -i --env PGPASSWORD \
        "$PGPLAN_CONTAINER_NAME" psql "${PSQL_ARGS[@]}" < "$STDIN_FILE"
else
    PGPASSWORD="$PGPLAN_CONTAINER_PASSWORD" docker exec -i --env PGPASSWORD \
        "$PGPLAN_CONTAINER_NAME" psql "${PSQL_ARGS[@]}"
fi
