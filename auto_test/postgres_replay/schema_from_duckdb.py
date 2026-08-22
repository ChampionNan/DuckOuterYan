#!/usr/bin/env python3
"""Render a small, PostgreSQL-compatible schema from DuckDB metadata.

The caller exports ``information_schema.columns`` and primary/unique
constraints to CSV.  Keeping this conversion separate makes the loader easy
to test and avoids adding a Python package dependency on experiment servers.
Unknown types and malformed metadata fail closed instead of being coerced.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


class SchemaError(ValueError):
    """Raised when DuckDB metadata cannot be represented safely."""


@dataclass(frozen=True)
class Column:
    name: str
    pg_type: str
    nullable: bool
    ordinal: int


@dataclass(frozen=True)
class Coercion:
    table: str
    column: str
    source_type: str
    pg_type: str


# The DuckDB JOB parquet files encode these nullable, conceptually integral
# IMDb fields as DOUBLE.  PostgreSQL does not define integer operators such as
# modulo for DOUBLE PRECISION, so the sampled-plan schema restores their
# conceptual type after the loader proves an exact BIGINT round trip.  Keep
# this list explicit: an unfamiliar floating-point field must be reviewed
# rather than silently changing its type.
_JOB_INTEGRAL_DOUBLE_COLUMNS = {
    "aka_title": {
        "production_year",
        "episode_of_id",
        "season_nr",
        "episode_nr",
    },
    "cast_info": {"person_role_id", "nr_order"},
    "char_name": {"imdb_id"},
    "company_name": {"imdb_id"},
    "name": {"imdb_id"},
    "title": {
        "production_year",
        "imdb_id",
        "episode_of_id",
        "season_nr",
        "episode_nr",
    },
}

_NATIVE_INTEGRAL_TYPES = {
    "TINYINT",
    "UTINYINT",
    "SMALLINT",
    "USMALLINT",
    "INTEGER",
    "INT",
    "UINTEGER",
    "BIGINT",
    "UBIGINT",
    "HUGEINT",
    "UHUGEINT",
}


_SIZED_TYPE = re.compile(r"^(VARCHAR|CHAR|CHARACTER|BIT)\s*\((\d+)\)$")
_DECIMAL_TYPE = re.compile(r"^(?:DECIMAL|NUMERIC)\s*\((\d+)\s*,\s*(\d+)\)$")


def quote_identifier(value: str) -> str:
    if not value or "\x00" in value or any(ord(char) < 32 for char in value):
        raise SchemaError("SQL identifier must be non-empty and contain no control characters")
    return '"{}"'.format(value.replace('"', '""'))


def postgres_type(duckdb_type: str) -> str:
    normalized = " ".join(duckdb_type.upper().split())
    direct = {
        "BOOLEAN": "BOOLEAN",
        "BOOL": "BOOLEAN",
        "TINYINT": "SMALLINT",
        "UTINYINT": "SMALLINT",
        "SMALLINT": "SMALLINT",
        "USMALLINT": "INTEGER",
        "INTEGER": "INTEGER",
        "INT": "INTEGER",
        "UINTEGER": "BIGINT",
        "BIGINT": "BIGINT",
        "UBIGINT": "NUMERIC(20, 0)",
        "HUGEINT": "NUMERIC(38, 0)",
        "UHUGEINT": "NUMERIC(39, 0)",
        "REAL": "REAL",
        "FLOAT": "REAL",
        "DOUBLE": "DOUBLE PRECISION",
        "DOUBLE PRECISION": "DOUBLE PRECISION",
        "VARCHAR": "VARCHAR",
        "CHAR": "CHAR",
        "CHARACTER": "CHAR",
        "TEXT": "TEXT",
        "BLOB": "BYTEA",
        "DATE": "DATE",
        "TIME": "TIME",
        "TIME WITH TIME ZONE": "TIME WITH TIME ZONE",
        "TIMETZ": "TIME WITH TIME ZONE",
        "TIMESTAMP": "TIMESTAMP",
        "DATETIME": "TIMESTAMP",
        "TIMESTAMP_S": "TIMESTAMP",
        "TIMESTAMP_MS": "TIMESTAMP",
        "TIMESTAMP_NS": "TIMESTAMP",
        "TIMESTAMP WITH TIME ZONE": "TIMESTAMP WITH TIME ZONE",
        "TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE",
        "INTERVAL": "INTERVAL",
        "UUID": "UUID",
    }
    if normalized in direct:
        return direct[normalized]

    decimal = _DECIMAL_TYPE.fullmatch(normalized)
    if decimal:
        precision = int(decimal.group(1))
        scale = int(decimal.group(2))
        if precision < 1 or precision > 1000 or scale < 0 or scale > precision:
            raise SchemaError("invalid decimal type: {}".format(duckdb_type))
        return "NUMERIC({}, {})".format(precision, scale)

    sized = _SIZED_TYPE.fullmatch(normalized)
    if sized:
        size = int(sized.group(2))
        if size < 1:
            raise SchemaError("invalid sized type: {}".format(duckdb_type))
        base = sized.group(1)
        if base in ("CHAR", "CHARACTER"):
            base = "CHAR"
        elif base == "BIT":
            base = "BIT"
        return "{}({})".format(base, size)

    raise SchemaError("unsupported DuckDB type: {}".format(duckdb_type))


def _column_type(
    family: str, table: str, column: str, duckdb_type: str
) -> tuple[str, Coercion | None]:
    normalized = " ".join(duckdb_type.upper().split())
    if family != "job":
        return postgres_type(duckdb_type), None

    reviewed = column in _JOB_INTEGRAL_DOUBLE_COLUMNS.get(table, set())
    if normalized in ("DOUBLE", "DOUBLE PRECISION"):
        if not reviewed:
            raise SchemaError(
                "JOB column {}.{} uses DOUBLE without a reviewed integral override".format(
                    table, column
                )
            )
        return "BIGINT", Coercion(table, column, normalized, "BIGINT")

    if reviewed and normalized not in _NATIVE_INTEGRAL_TYPES:
        raise SchemaError(
            "conceptually integral JOB column {}.{} has unreviewed source type {}".format(
                table, column, duckdb_type
            )
        )
    return postgres_type(duckdb_type), None


def _read_columns(
    path: Path, expected_tables: list[str], family: str
) -> tuple[dict[str, list[Column]], list[Coercion]]:
    expected = {name.casefold(): name.casefold() for name in expected_tables}
    if len(expected) != len(expected_tables):
        raise SchemaError("requested table names must be unique ignoring case")
    columns: dict[str, list[Column]] = defaultdict(list)
    coercions: list[Coercion] = []
    source_spellings: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        required = {"table_name", "column_name", "data_type", "is_nullable", "ordinal_position"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise SchemaError("column metadata is missing required fields")
        for row in reader:
            table_source = row["table_name"]
            table = table_source.casefold()
            if table not in expected:
                raise SchemaError("unexpected table in column metadata: {}".format(table_source))
            prior = source_spellings.setdefault(table, table_source)
            if prior != table_source:
                raise SchemaError(
                    "multiple DuckDB tables differ only by case: {}, {}".format(prior, table_source)
                )
            nullable_text = row["is_nullable"].upper()
            if nullable_text not in ("YES", "NO"):
                raise SchemaError(
                    "{}.{} has invalid is_nullable value {}".format(
                        table_source, row["column_name"], row["is_nullable"]
                    )
                )
            try:
                ordinal = int(row["ordinal_position"])
            except ValueError as exc:
                raise SchemaError(
                    "{}.{} has invalid ordinal_position".format(table_source, row["column_name"])
                ) from exc
            column_name = row["column_name"]
            pg_type, coercion = _column_type(
                family, table, column_name.casefold(), row["data_type"]
            )
            columns[table].append(
                Column(
                    name=column_name,
                    pg_type=pg_type,
                    nullable=nullable_text == "YES",
                    ordinal=ordinal,
                )
            )
            if coercion is not None:
                # Preserve the source spelling in diagnostics while matching
                # reviewed identities case-insensitively.
                coercions.append(
                    Coercion(table_source.casefold(), column_name, coercion.source_type, coercion.pg_type)
                )

    missing = sorted(set(expected) - set(columns))
    if missing:
        raise SchemaError("DuckDB database is missing required table(s): {}".format(", ".join(missing)))
    for table, table_columns in columns.items():
        table_columns.sort(key=lambda column: column.ordinal)
        ordinals = [column.ordinal for column in table_columns]
        if ordinals != list(range(1, len(table_columns) + 1)):
            raise SchemaError("{}.ordinal_position must be contiguous from 1".format(table))
        names = [column.name.casefold() for column in table_columns]
        if len(names) != len(set(names)):
            raise SchemaError("{} has duplicate column names ignoring case".format(table))
        if family == "job" and table in _JOB_INTEGRAL_DOUBLE_COLUMNS:
            missing_reviewed = sorted(_JOB_INTEGRAL_DOUBLE_COLUMNS[table] - set(names))
            if missing_reviewed:
                raise SchemaError(
                    "JOB table {} is missing reviewed integral column(s): {}".format(
                        table, ", ".join(missing_reviewed)
                    )
                )
    return dict(columns), coercions


def _read_constraints(
    path: Path, columns: dict[str, list[Column]]
) -> dict[str, list[tuple[str, list[str]]]]:
    grouped: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        required = {"table_name", "constraint_index", "constraint_type", "column_name"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise SchemaError("constraint metadata is missing required fields")
        for row in reader:
            table = row["table_name"].casefold()
            if table not in columns:
                raise SchemaError("constraint references unexpected table: {}".format(row["table_name"]))
            kind = row["constraint_type"].upper()
            if kind not in ("PRIMARY KEY", "UNIQUE"):
                raise SchemaError("unsupported constraint type: {}".format(row["constraint_type"]))
            column_lookup = {column.name.casefold(): column.name for column in columns[table]}
            column_key = row["column_name"].casefold()
            if column_key not in column_lookup:
                raise SchemaError(
                    "constraint on {} references missing column {}".format(table, row["column_name"])
                )
            key = (table, row["constraint_index"], kind)
            grouped[key].append(column_lookup[column_key])

    result: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for (table, _index, kind), names in sorted(grouped.items()):
        if len(names) != len({name.casefold() for name in names}):
            raise SchemaError("constraint on {} contains a duplicate column".format(table))
        result[table].append((kind, names))
    return dict(result)


def render_schema(
    metadata: Path,
    constraints: Path,
    schema: str,
    tables: list[str],
    replace: bool,
    provenance: str,
    family: str = "generic",
) -> tuple[str, list[Coercion]]:
    columns, coercions = _read_columns(metadata, tables, family)
    keys = _read_constraints(constraints, columns)
    quoted_schema = quote_identifier(schema)
    statements: list[str] = []
    if replace:
        statements.append("DROP SCHEMA IF EXISTS {} CASCADE;".format(quoted_schema))
    statements.append("CREATE SCHEMA IF NOT EXISTS {};".format(quoted_schema))
    statements.append(
        "COMMENT ON SCHEMA {} IS {};".format(
            quoted_schema, "'{}'".format(provenance.replace("'", "''"))
        )
    )
    for requested in tables:
        table = requested.casefold()
        definitions = []
        for column in columns[table]:
            definition = "{} {}".format(quote_identifier(column.name), column.pg_type)
            if not column.nullable:
                definition += " NOT NULL"
            definitions.append(definition)
        for kind, names in keys.get(table, []):
            definitions.append(
                "{} ({})".format(kind, ", ".join(quote_identifier(name) for name in names))
            )
        statements.append(
            "CREATE TABLE {}.{} (\n    {}\n);".format(
                quoted_schema,
                quote_identifier(table),
                ",\n    ".join(definitions),
            )
        )
        for coercion in coercions:
            if coercion.table != table:
                continue
            statements.append(
                "COMMENT ON COLUMN {}.{}.{} IS {};".format(
                    quoted_schema,
                    quote_identifier(table),
                    quote_identifier(coercion.column),
                    "'{}'".format(
                        (
                            "DuckYan PGPlan validated integral coercion: "
                            "DuckDB {} to PostgreSQL {}; sampled non-NULL values "
                            "must round-trip exactly"
                        )
                        .format(coercion.source_type, coercion.pg_type)
                        .replace("'", "''")
                    ),
                )
            )
    return "\n\n".join(statements) + "\n", coercions


def write_coercions(path: Path, coercions: list[Coercion]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(["table_name", "column_name", "source_type", "pg_type", "validation"])
        for coercion in coercions:
            writer.writerow(
                [
                    coercion.table,
                    coercion.column,
                    coercion.source_type,
                    coercion.pg_type,
                    "sampled-nonnull-exact-bigint-roundtrip",
                ]
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--constraints", required=True, type=Path)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--table", action="append", dest="tables", required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--family", choices=("generic", "graph", "tpch", "tpcds", "job"), default="generic")
    parser.add_argument("--coercions-out", type=Path)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        rendered, coercions = render_schema(
            args.metadata,
            args.constraints,
            args.schema,
            args.tables,
            args.replace,
            args.provenance,
            args.family,
        )
        args.out.write_text(rendered, encoding="utf-8")
        if args.coercions_out is not None:
            write_coercions(args.coercions_out, coercions)
    except (OSError, SchemaError) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
