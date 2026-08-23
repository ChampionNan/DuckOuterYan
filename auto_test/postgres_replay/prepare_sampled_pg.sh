#!/usr/bin/env bash
# Prepare isolated, row-capped graph/TPC-DS/JOB schemas for PGPlan capture.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../configs.sh
source "$SCRIPT_DIR/../configs.sh"

FAMILY=""
DUCKDB_DB=""
ROW_CAP="${PGPLAN_SAMPLE_ROWS:-1000}"
PG_DSN="${PG_DSN:-}"
PSQL_BIN="${PSQL_BIN:-psql}"
DUCKDB_BIN="${DUCKDB_BIN:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EXPECTED_VERSION="${PGPLAN_VERSION_NUM:-${PG_REPLAY_VERSION_NUM:-160002}}"
FORCE=0
MANIFEST=""

usage() {
    cat <<'USAGE'
Usage:
  prepare_sampled_pg.sh --family graph|tpcds|job --duckdb-db PATH
      [--rows N] [--pg-dsn DSN] [--force] [--manifest PATH]

The loader copies at most N rows per table, in DuckDB physical row order, into
an isolated PostgreSQL schema:

  graph -> pgplan_graph
  tpcds -> pgplan_tpcds
  job   -> pgplan_job

It reproduces columns, NULL constraints, and primary/unique keys exposed by
the DuckDB database, verifies every loaded cardinality, and runs ANALYZE.
Unknown DuckDB types, missing tables, partial loads, or PostgreSQL versions
other than 16.2 fail closed. No pip package or host psql is required in Docker
mode; PSQL_BIN may be docker_psql.sh.

An existing family schema is never replaced without --force. In external mode,
replacement additionally requires PGPLAN_FORCE_SAMPLED_DATA=1
(PG_REPLAY_FORCE_DATA=1 remains a compatibility alias).
USAGE
}

die() {
    echo "ERROR: $*" >&2
    exit 2
}

require_executable() {
    local executable="$1" label="$2"
    if [[ "$executable" == */* ]]; then
        [ -x "$executable" ] || die "$label is not executable: $executable"
    else
        command -v "$executable" >/dev/null 2>&1 || die "$label not found: $executable"
    fi
}

while [ $# -gt 0 ]; do
    case "$1" in
        --family)
            [ $# -ge 2 ] || die "$1 requires a value"
            FAMILY="$2"
            shift 2
            ;;
        --duckdb-db)
            [ $# -ge 2 ] || die "$1 requires a value"
            DUCKDB_DB="$2"
            shift 2
            ;;
        --rows)
            [ $# -ge 2 ] || die "$1 requires a value"
            ROW_CAP="$2"
            shift 2
            ;;
        --pg-dsn)
            [ $# -ge 2 ] || die "$1 requires a value"
            PG_DSN="$2"
            shift 2
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --manifest)
            [ $# -ge 2 ] || die "$1 requires a value"
            MANIFEST="$2"
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

case "$FAMILY" in
    graph)
        PG_SCHEMA="pgplan_graph"
        TABLES=(r1 r2 r3 r4 r5 r6 r7 r8 r9 r10)
        ;;
    tpcds)
        PG_SCHEMA="pgplan_tpcds"
        TABLES=(
            call_center catalog_page catalog_returns catalog_sales customer
            customer_address customer_demographics date_dim
            household_demographics income_band inventory item promotion reason
            ship_mode store store_returns store_sales time_dim warehouse
            web_page web_returns web_sales web_site
        )
        ;;
    job)
        PG_SCHEMA="pgplan_job"
        TABLES=(
            aka_name aka_title cast_info char_name comp_cast_type company_name
            company_type complete_cast info_type keyword kind_type link_type
            movie_companies movie_info movie_info_idx movie_keyword movie_link
            name person_info role_type title
        )
        ;;
    '') die "--family is required" ;;
    *) die "--family must be graph, tpcds, or job" ;;
esac

[ -n "$DUCKDB_DB" ] || die "--duckdb-db is required"
[ -f "$DUCKDB_DB" ] || die "DuckDB database does not exist: $DUCKDB_DB"
[ -n "$PG_DSN" ] || die "--pg-dsn is required (or set PG_DSN)"
[[ "$ROW_CAP" =~ ^[1-9][0-9]*$ ]] || die "--rows must be a positive integer"
[ "$EXPECTED_VERSION" = "160002" ] || die "PGPlan sampled data requires PostgreSQL 16.2"
require_executable "$DUCKDB_BIN" duckdb
require_executable "$PSQL_BIN" psql
require_executable "$PYTHON_BIN" python3

TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/duckyan-pgplan-sample.XXXXXX")"
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

ACTUAL_VERSION="$({
    "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
        --command="SELECT current_setting('server_version_num');"
} | tr -d '[:space:]')"
[ "$ACTUAL_VERSION" = "$EXPECTED_VERSION" ] || \
    die "PostgreSQL server_version_num mismatch: expected $EXPECTED_VERSION, got ${ACTUAL_VERSION:-<empty>}"

SCHEMA_EXISTS="$({
    "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
        --command="SELECT count(*) FROM information_schema.schemata WHERE schema_name = '$PG_SCHEMA';"
} | tr -d '[:space:]')"
case "$SCHEMA_EXISTS" in 0|1) ;; *) die "could not inspect PostgreSQL schema $PG_SCHEMA" ;; esac
if [ "$SCHEMA_EXISTS" = "1" ] && [ "$FORCE" -ne 1 ]; then
    die "PostgreSQL schema $PG_SCHEMA already exists; pass --force to replace only that isolated schema"
fi
if [ "$SCHEMA_EXISTS" = "1" ] && [ "$FORCE" -eq 1 ] && \
        [ "${PGPLAN_SETUP:-${PG_REPLAY_SETUP:-source}}" = "external" ] && \
        [ "${PGPLAN_FORCE_SAMPLED_DATA:-${PGPLAN_FORCE_DATA:-${PG_REPLAY_FORCE_DATA:-0}}}" != "1" ]; then
    die "external PostgreSQL schema replacement requires PGPLAN_FORCE_SAMPLED_DATA=1"
fi

METADATA="$TEMP_ROOT/columns.csv"
CONSTRAINTS="$TEMP_ROOT/constraints.csv"
DDL="$TEMP_ROOT/schema.sql"
COERCIONS="$TEMP_ROOT/coercions.tsv"

TABLE_IN=""
for table in "${TABLES[@]}"; do
    if [ -n "$TABLE_IN" ]; then
        TABLE_IN="$TABLE_IN,"
    fi
    TABLE_IN="$TABLE_IN'$table'"
done

escape_duckdb_string() {
    printf '%s' "$1" | sed "s/'/''/g"
}

METADATA_ESCAPED="$(escape_duckdb_string "$METADATA")"
CONSTRAINTS_ESCAPED="$(escape_duckdb_string "$CONSTRAINTS")"
"$DUCKDB_BIN" "$DUCKDB_DB" -no-init -bail -c "
    COPY (
        SELECT table_name, column_name, data_type, is_nullable, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'main' AND lower(table_name) IN ($TABLE_IN)
        ORDER BY lower(table_name), ordinal_position
    ) TO '$METADATA_ESCAPED' (FORMAT CSV, HEADER TRUE);
    COPY (
        SELECT c.table_name, c.constraint_index, c.constraint_type,
               unnest(c.constraint_column_names) AS column_name,
               generate_subscripts(c.constraint_column_names, 1) AS column_ordinal
        FROM duckdb_constraints() c
        WHERE c.schema_name = 'main'
          AND lower(c.table_name) IN ($TABLE_IN)
          AND c.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        ORDER BY lower(c.table_name), c.constraint_index, column_ordinal
    ) TO '$CONSTRAINTS_ESCAPED' (FORMAT CSV, HEADER TRUE);
" >/dev/null
[ -s "$METADATA" ] || die "DuckDB returned no column metadata"
[ -s "$CONSTRAINTS" ] || die "DuckDB returned no constraint metadata header"

SCHEMA_ARGS=()
for table in "${TABLES[@]}"; do
    SCHEMA_ARGS+=(--table "$table")
done
if [ "$FORCE" -eq 1 ]; then
    SCHEMA_ARGS+=(--replace)
fi
"$PYTHON_BIN" "$SCRIPT_DIR/schema_from_duckdb.py" \
    --metadata "$METADATA" \
    --constraints "$CONSTRAINTS" \
    --schema "$PG_SCHEMA" \
    --family "$FAMILY" \
    --provenance "DuckYan PGPlan $FAMILY sample, at most $ROW_CAP rows per table" \
    --coercions-out "$COERCIONS" \
    --out "$DDL" \
    "${SCHEMA_ARGS[@]}"
[ -s "$COERCIONS" ] || die "schema converter returned no coercion metadata"

quote_duckdb_identifier() {
    local identifier="$1"
    identifier="${identifier//\"/\"\"}"
    printf '"%s"' "$identifier"
}

# `ORDER BY rowid LIMIT N` plans as TOP_N over a full scan. Use the bounded
# physical rowid range [0, N) consistently for row counts, coercion checks, and
# export. Rowid gaps, if present, are part of this deterministic sample recipe.
ROWID_COUNTS="$TEMP_ROOT/rowid_counts.tsv"
printf 'table\tsample_rows\n' > "$ROWID_COUNTS"
for table in "${TABLES[@]}"; do
    SAMPLE_ROWS="$({
        "$DUCKDB_BIN" "$DUCKDB_DB" -no-init -bail -csv -noheader -c \
            "SELECT count(*) FROM \"$table\"
             WHERE rowid >= 0 AND rowid < $ROW_CAP;"
    } | tr -d '[:space:]')"
    case "$SAMPLE_ROWS" in
        ''|*[!0-9]*) die "could not count bounded physical rowid sample for $table: ${SAMPLE_ROWS:-<empty>}" ;;
    esac
    printf '%s\t%s\n' "$table" "$SAMPLE_ROWS" >> "$ROWID_COUNTS"
done

COERCION_COUNT=0
while IFS=$'\t' read -r coercion_table column source_type pg_type validation; do
    [ "$coercion_table" = "table_name" ] && continue
    COERCION_COUNT=$((COERCION_COUNT + 1))
    [ "$source_type" = "DOUBLE" ] || [ "$source_type" = "DOUBLE PRECISION" ] || \
        die "unsupported sampled coercion source for $coercion_table.$column: $source_type"
    [ "$pg_type" = "BIGINT" ] || \
        die "unsupported sampled coercion target for $coercion_table.$column: $pg_type"
    [ "$validation" = "sampled-nonnull-exact-bigint-roundtrip" ] || \
        die "unsupported sampled coercion validation for $coercion_table.$column: $validation"

    quoted_column="$(quote_duckdb_identifier "$column")"
    INVALID_ROWS="$({
        "$DUCKDB_BIN" "$DUCKDB_DB" -no-init -bail -csv -noheader -c \
            "SELECT count(*)
             FROM (SELECT * FROM \"$coercion_table\"
                   WHERE rowid >= 0 AND rowid < $ROW_CAP
                   ORDER BY rowid) AS pgplan_sample
             WHERE $quoted_column IS NOT NULL
               AND (TRY_CAST($quoted_column AS BIGINT) IS NULL
                    OR CAST(TRY_CAST($quoted_column AS BIGINT) AS DOUBLE)
                       IS DISTINCT FROM $quoted_column);"
    } | tr -d '[:space:]')"
    case "$INVALID_ROWS" in ''|*[!0-9]*) die "could not validate sampled coercion $coercion_table.$column" ;; esac
    [ "$INVALID_ROWS" = "0" ] || \
        die "$coercion_table.$column has $INVALID_ROWS sampled value(s) that do not round-trip exactly as BIGINT"
done < "$COERCIONS"

# Validate every material type change before replacing or populating the
# isolated PostgreSQL schema.  A rejected sample therefore cannot leave a
# partially loaded schema behind.
"$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" --file="$DDL"

if [ -n "$MANIFEST" ]; then
    mkdir -p "$(dirname "$MANIFEST")"
    printf 'family\tpg_schema\ttable\trow_cap\tloaded_rows\tduckdb_db\tvalidated_integral_coercions\n' > "$MANIFEST"
fi

echo "[pgplan] loading $FAMILY sample into PostgreSQL schema $PG_SCHEMA (row cap=$ROW_CAP)"
ANALYZE_TARGETS=""
for table in "${TABLES[@]}"; do
    DATA_FILE="$TEMP_ROOT/$table.csv"
    DATA_FILE_ESCAPED="$(escape_duckdb_string "$DATA_FILE")"
    REPLACEMENTS=""
    TABLE_COERCIONS=""
    while IFS=$'\t' read -r coercion_table column source_type pg_type validation; do
        [ "$coercion_table" = "table_name" ] && continue
        [ "$coercion_table" = "$table" ] || continue
        [ "$source_type" = "DOUBLE" ] || [ "$source_type" = "DOUBLE PRECISION" ] || \
            die "unsupported sampled coercion source for $table.$column: $source_type"
        [ "$pg_type" = "BIGINT" ] || die "unsupported sampled coercion target for $table.$column: $pg_type"
        [ "$validation" = "sampled-nonnull-exact-bigint-roundtrip" ] || \
            die "unsupported sampled coercion validation for $table.$column: $validation"

        quoted_column="$(quote_duckdb_identifier "$column")"
        if [ -n "$REPLACEMENTS" ]; then
            REPLACEMENTS="$REPLACEMENTS, "
            TABLE_COERCIONS="$TABLE_COERCIONS,"
        fi
        REPLACEMENTS="${REPLACEMENTS}CAST($quoted_column AS BIGINT) AS $quoted_column"
        TABLE_COERCIONS="${TABLE_COERCIONS}${column}:${source_type}->${pg_type}"
    done < "$COERCIONS"

    SAMPLE_QUERY="SELECT * FROM \"$table\"
                  WHERE rowid >= 0 AND rowid < $ROW_CAP
                  ORDER BY rowid"
    if [ -n "$REPLACEMENTS" ]; then
        SAMPLE_QUERY="SELECT * REPLACE ($REPLACEMENTS) FROM ($SAMPLE_QUERY) AS pgplan_sample"
    fi
    "$DUCKDB_BIN" "$DUCKDB_DB" -no-init -bail -c "
        COPY (
            $SAMPLE_QUERY
        ) TO '$DATA_FILE_ESCAPED' (FORMAT CSV, HEADER FALSE);
    " >/dev/null

    EXPECTED_ROWS="$(awk -F '\t' -v wanted="$table" \
        '$1 == wanted {print $2; exit}' "$ROWID_COUNTS")"
    case "$EXPECTED_ROWS" in ''|*[!0-9]*) die "could not count sampled DuckDB table $table" ;; esac

    "$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
        --command="\copy \"$PG_SCHEMA\".\"$table\" FROM STDIN WITH (FORMAT csv, NULL '')" \
        < "$DATA_FILE"
    ACTUAL_ROWS="$({
        "$PSQL_BIN" -X -qAt --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
            --command="SELECT count(*) FROM \"$PG_SCHEMA\".\"$table\";"
    } | tr -d '[:space:]')"
    [ "$ACTUAL_ROWS" = "$EXPECTED_ROWS" ] || \
        die "$PG_SCHEMA.$table cardinality mismatch: expected $EXPECTED_ROWS, got ${ACTUAL_ROWS:-<empty>}"

    if [ -n "$ANALYZE_TARGETS" ]; then
        ANALYZE_TARGETS="$ANALYZE_TARGETS, "
    fi
    ANALYZE_TARGETS="$ANALYZE_TARGETS\"$PG_SCHEMA\".\"$table\""
    if [ -n "$MANIFEST" ]; then
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$FAMILY" "$PG_SCHEMA" "$table" "$ROW_CAP" "$ACTUAL_ROWS" "$DUCKDB_DB" "$TABLE_COERCIONS" \
            >> "$MANIFEST"
    fi
done

"$PSQL_BIN" -X -q --set=ON_ERROR_STOP=1 --dbname="$PG_DSN" \
    --command="ANALYZE $ANALYZE_TARGETS;"

PLAN_DATA="$FAMILY-duckdb-sample-$ROW_CAP"
echo "[PGPLAN_DATA] {\"family\":\"$FAMILY\",\"schema\":\"$PG_SCHEMA\",\"plan_data\":\"$PLAN_DATA\",\"row_cap\":$ROW_CAP,\"postgres_version_num\":$ACTUAL_VERSION,\"validated_integral_coercions\":$COERCION_COUNT}"
