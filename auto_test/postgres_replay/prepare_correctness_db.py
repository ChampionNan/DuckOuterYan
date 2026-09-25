#!/usr/bin/env python3
"""Build a bounded small DuckDB database for PGPlan correctness runs.

Graph and JOB are copied from the same physical-row prefix consumed by
prepare_sampled_pg.sh.  TPC-H and TPC-DS use referentially coherent SF0.01
generator data.  Every family clones the target database DDL first, so target
column definitions and keys are retained.  The output is published only after
schema, data, constraint, and bounded-result validation succeeds.

The rowid prefixes and generator bases are deterministic.  TPC-DS and JOB may
also include bounded target-result witnesses selected by the current DuckDB
execution, so a witness-enriched database is a captured fixture rather than a
claim of byte-for-byte reproducibility across engines or runs.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable, Sequence

from normalize_plan import PlanError, _query_alias_occurrences, canonicalize_query


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

FAMILY_TABLES: dict[str, tuple[str, ...]] = {
    "graph": tuple(f"r{index}" for index in range(1, 11)),
    "tpch": (
        "region",
        "nation",
        "supplier",
        "customer",
        "part",
        "partsupp",
        "orders",
        "lineitem",
    ),
    "tpcds": (
        "call_center",
        "catalog_page",
        "catalog_returns",
        "catalog_sales",
        "customer",
        "customer_address",
        "customer_demographics",
        "date_dim",
        "household_demographics",
        "income_band",
        "inventory",
        "item",
        "promotion",
        "reason",
        "ship_mode",
        "store",
        "store_returns",
        "store_sales",
        "time_dim",
        "warehouse",
        "web_page",
        "web_returns",
        "web_sales",
        "web_site",
    ),
    "job": (
        "aka_name",
        "aka_title",
        "cast_info",
        "char_name",
        "comp_cast_type",
        "company_name",
        "company_type",
        "complete_cast",
        "info_type",
        "keyword",
        "kind_type",
        "link_type",
        "movie_companies",
        "movie_info",
        "movie_info_idx",
        "movie_keyword",
        "movie_link",
        "name",
        "person_info",
        "role_type",
        "title",
    ),
}

TPCH_CARDINALITIES = {
    "region": 5,
    "nation": 25,
    "supplier": 100,
    "customer": 1_500,
    "part": 2_000,
    "partsupp": 8_000,
    "orders": 15_000,
    "lineitem": 60_175,
}

TPCDS_CARDINALITIES = {
    "call_center": 1,
    "catalog_page": 11_718,
    "catalog_returns": 1_358,
    "catalog_sales": 14_313,
    "customer": 1_000,
    "customer_address": 500,
    "customer_demographics": 19_208,
    "date_dim": 73_049,
    "household_demographics": 7_200,
    "income_band": 20,
    "inventory": 23_490,
    "item": 180,
    "promotion": 3,
    "reason": 1,
    "ship_mode": 20,
    "store": 1,
    "store_returns": 2_810,
    "store_sales": 28_810,
    "time_dim": 86_400,
    "warehouse": 1,
    "web_page": 1,
    "web_returns": 679,
    "web_sales": 7_212,
    "web_site": 1,
}

DEFAULT_ROWS = {"graph": 500, "job": 1_000}
DEFAULT_MAX_RESULT_ROWS = 2_000_000
DEFAULT_QUERY_TIMEOUT = 30.0
DEFAULT_WITNESS_ROWS = 1

_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


class BuildError(RuntimeError):
    """A correctness database could not be built safely."""


def quote_identifier(value: str) -> str:
    return '"{}"'.format(value.replace('"', '""'))


def quote_literal(value: str) -> str:
    return "'{}'".format(value.replace("'", "''"))


def positive_int(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return parsed


def default_duckdb_binary() -> str:
    configured = os.environ.get("DUCKDB_BIN")
    if configured:
        return configured
    for candidate in (
        REPO_ROOT / "build" / "release" / "duckdb",
        REPO_ROOT / "build" / "debug" / "duckdb",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "duckdb"


def resolve_executable(value: str) -> Path:
    if os.sep in value or (os.altsep and os.altsep in value):
        candidate = Path(value).expanduser().resolve()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise BuildError(f"DuckDB binary is not executable: {candidate}")
        return candidate
    found = shutil.which(value)
    if not found:
        raise BuildError(f"DuckDB binary was not found: {value}")
    return Path(found).resolve()


class DuckDBCLI:
    def __init__(self, executable: Path) -> None:
        self.executable = executable

    def run(
        self,
        database: Path,
        sql: str,
        *,
        timeout: float = 120.0,
        csv_output: bool = False,
    ) -> str:
        command = [
            str(self.executable),
            str(database),
            "-no-init",
            "-bail",
        ]
        if csv_output:
            command.extend(["-csv", "-header"])
        command.extend(["-c", sql])
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise BuildError(
                f"DuckDB command exceeded its {timeout:g}-second limit"
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise BuildError(f"DuckDB command failed: {detail}")
        return result.stdout

    def rows(
        self, database: Path, sql: str, *, timeout: float = 120.0
    ) -> list[dict[str, str]]:
        output = self.run(database, sql, timeout=timeout, csv_output=True)
        return list(csv.DictReader(io.StringIO(output)))


def sql_table_filter(tables: Sequence[str]) -> str:
    return ", ".join(quote_literal(table.casefold()) for table in tables)


def table_catalog_sql(tables: Sequence[str]) -> str:
    return f"""
        SELECT table_name, sql
        FROM duckdb_tables()
        WHERE schema_name = 'main'
          AND lower(table_name) IN ({sql_table_filter(tables)})
        ORDER BY lower(table_name);
    """


def column_catalog_sql(tables: Sequence[str]) -> str:
    return f"""
        SELECT lower(table_name) AS table_name, ordinal_position, column_name,
               data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'main'
          AND lower(table_name) IN ({sql_table_filter(tables)})
        ORDER BY lower(table_name), ordinal_position;
    """


def key_catalog_sql(tables: Sequence[str]) -> str:
    return f"""
        SELECT lower(table_name) AS table_name, constraint_type,
               array_to_string(constraint_column_names, ',') AS columns
        FROM duckdb_constraints()
        WHERE schema_name = 'main'
          AND lower(table_name) IN ({sql_table_filter(tables)})
          AND constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        ORDER BY lower(table_name), constraint_type, columns;
    """


def count_tables_sql(tables: Sequence[str]) -> str:
    branches = [
        "SELECT {} AS table_name, count(*)::UBIGINT AS rows FROM {}".format(
            quote_literal(table.casefold()), quote_identifier(table)
        )
        for table in tables
    ]
    return "\nUNION ALL\n".join(branches) + ";"


def parse_counts(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        table = row["table_name"].casefold()
        try:
            count = int(row["rows"], 10)
        except (KeyError, ValueError) as exc:
            raise BuildError(f"invalid DuckDB table count row: {row}") from exc
        if table in counts:
            raise BuildError(f"duplicate table count for {table}")
        counts[table] = count
    return counts


def parse_keys(rows: Iterable[dict[str, str]]) -> set[tuple[str, str, tuple[str, ...]]]:
    keys: set[tuple[str, str, tuple[str, ...]]] = set()
    for row in rows:
        columns = tuple(column for column in row["columns"].split(",") if column)
        keys.add((row["table_name"].casefold(), row["constraint_type"], columns))
    return keys


def validate_source_tables(
    catalog_rows: Sequence[dict[str, str]], tables: Sequence[str]
) -> dict[str, tuple[str, str]]:
    requested = {table.casefold() for table in tables}
    catalog: dict[str, tuple[str, str]] = {}
    for row in catalog_rows:
        actual = row.get("table_name", "")
        ddl = row.get("sql", "")
        folded = actual.casefold()
        if not actual or not ddl:
            raise BuildError("source database returned an incomplete table definition")
        if folded in catalog:
            raise BuildError(f"source database has ambiguous table name: {actual}")
        catalog[folded] = (actual, ddl)
    missing = sorted(requested - catalog.keys())
    extra = sorted(catalog.keys() - requested)
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise BuildError("source family schema mismatch: " + "; ".join(details))
    return catalog


def read_schema_authority(
    cli: DuckDBCLI, source: Path, tables: Sequence[str]
) -> tuple[
    dict[str, tuple[str, str]],
    list[dict[str, str]],
    set[tuple[str, str, tuple[str, ...]]],
    dict[str, int],
]:
    catalog = validate_source_tables(cli.rows(source, table_catalog_sql(tables)), tables)
    columns = cli.rows(source, column_catalog_sql(tables))
    keys = parse_keys(cli.rows(source, key_catalog_sql(tables)))
    counts = parse_counts(cli.rows(source, count_tables_sql(tables)))
    return catalog, columns, keys, counts


def clone_schema(
    cli: DuckDBCLI,
    output: Path,
    catalog: dict[str, tuple[str, str]],
    tables: Sequence[str],
) -> None:
    ddl = "\n".join(catalog[table.casefold()][1] for table in tables)
    cli.run(output, ddl)


def validate_cloned_schema(
    cli: DuckDBCLI,
    output: Path,
    tables: Sequence[str],
    source_columns: Sequence[dict[str, str]],
    source_keys: set[tuple[str, str, tuple[str, ...]]],
) -> set[tuple[str, str, tuple[str, ...]]]:
    output_columns = cli.rows(output, column_catalog_sql(tables))
    if list(source_columns) != output_columns:
        raise BuildError("output column schema differs from the target database")
    output_keys = parse_keys(cli.rows(output, key_catalog_sql(tables)))
    if source_keys != output_keys:
        missing = sorted(source_keys - output_keys)
        unexpected = sorted(output_keys - source_keys)
        raise BuildError(
            "output PRIMARY KEY/UNIQUE constraints differ from target: "
            f"missing={missing}, unexpected={unexpected}"
        )
    return output_keys


def comparable_columns(rows: Sequence[dict[str, str]]) -> list[tuple[str, str, str, str]]:
    return [
        (
            row["table_name"].casefold(),
            row["ordinal_position"],
            row["column_name"].casefold(),
            row["data_type"],
        )
        for row in rows
    ]


def insert_data(
    cli: DuckDBCLI,
    data_source: Path,
    output: Path,
    target_catalog: dict[str, tuple[str, str]],
    data_catalog: dict[str, tuple[str, str]],
    tables: Sequence[str],
    row_cap: int | None,
) -> None:
    source_alias = "pgplan_correctness_source"
    statements = [
        f"ATTACH {quote_literal(str(data_source))} AS {quote_identifier(source_alias)} (READ_ONLY);",
        "BEGIN TRANSACTION;",
    ]
    for table in tables:
        target_name = quote_identifier(target_catalog[table.casefold()][0])
        source_name = quote_identifier(data_catalog[table.casefold()][0])
        limit = "" if row_cap is None else f" LIMIT {row_cap}"
        statements.append(
            f"INSERT INTO main.{target_name} SELECT * FROM "
            f"{quote_identifier(source_alias)}.main.{source_name} "
            f"ORDER BY rowid{limit};"
        )
    statements.extend(
        [
            "COMMIT;",
            f"DETACH {quote_identifier(source_alias)};",
            "ANALYZE;",
            "CHECKPOINT;",
        ]
    )
    cli.run(output, "\n".join(statements), timeout=300.0)


def validate_data_contents(
    cli: DuckDBCLI,
    data_source: Path,
    output: Path,
    target_catalog: dict[str, tuple[str, str]],
    data_catalog: dict[str, tuple[str, str]],
    tables: Sequence[str],
    row_cap: int | None,
) -> None:
    source_alias = "pgplan_correctness_source"
    branches = []
    for table in tables:
        target_name = quote_identifier(target_catalog[table.casefold()][0])
        source_name = quote_identifier(data_catalog[table.casefold()][0])
        limit = "" if row_cap is None else f" LIMIT {row_cap}"
        expected = (
            f"SELECT * FROM {quote_identifier(source_alias)}.main.{source_name} "
            f"ORDER BY rowid{limit}"
        )
        missing = (
            f"SELECT * FROM ({expected}) AS expected "
            f"EXCEPT ALL SELECT * FROM main.{target_name}"
        )
        extra = (
            f"SELECT * FROM main.{target_name} EXCEPT ALL "
            f"SELECT * FROM ({expected}) AS expected"
        )
        branches.append(
            "SELECT {} AS table_name, "
            "(SELECT count(*) FROM ({}) AS missing_rows)::UBIGINT AS missing_rows, "
            "(SELECT count(*) FROM ({}) AS extra_rows)::UBIGINT AS extra_rows".format(
                quote_literal(table.casefold()), missing, extra
            )
        )
    sql = (
        f"ATTACH {quote_literal(str(data_source))} AS {quote_identifier(source_alias)} (READ_ONLY);\n"
        + "\nUNION ALL\n".join(branches)
        + ";"
    )
    deltas = cli.rows(output, sql, timeout=300.0)
    for delta in deltas:
        if delta["missing_rows"] != "0" or delta["extra_rows"] != "0":
            raise BuildError(
                "output contents differ from deterministic data source for "
                f"{delta['table_name']}: missing={delta['missing_rows']}, "
                f"extra={delta['extra_rows']}"
            )


def build_prefix_sample(
    cli: DuckDBCLI,
    source: Path,
    output: Path,
    tables: Sequence[str],
    row_cap: int,
) -> tuple[dict[str, int], dict[str, int], set[tuple[str, str, tuple[str, ...]]]]:
    catalog, source_columns, source_keys, source_counts = read_schema_authority(
        cli, source, tables
    )
    clone_schema(cli, output, catalog, tables)
    insert_data(cli, source, output, catalog, catalog, tables, row_cap)
    output_keys = validate_cloned_schema(
        cli, output, tables, source_columns, source_keys
    )
    output_counts = parse_counts(cli.rows(output, count_tables_sql(tables)))
    expected_counts = {
        table.casefold(): min(source_counts[table.casefold()], row_cap)
        for table in tables
    }
    if output_counts != expected_counts:
        raise BuildError(
            f"sample cardinality mismatch: expected {expected_counts}, got {output_counts}"
        )
    validate_data_contents(cli, source, output, catalog, catalog, tables, row_cap)
    return source_counts, output_counts, output_keys


def build_generated_sf001(
    cli: DuckDBCLI,
    schema_source: Path,
    generator: Path,
    output: Path,
    tables: Sequence[str],
    family: str,
) -> tuple[dict[str, int], dict[str, int], set[tuple[str, str, tuple[str, ...]]]]:
    if family == "tpch":
        call = "CALL dbgen(sf=0.01);"
        expected_counts = TPCH_CARDINALITIES
        generator_name = "TPC-H dbgen"
    elif family == "tpcds":
        call = "CALL dsdgen(sf=0.01);"
        expected_counts = TPCDS_CARDINALITIES
        generator_name = "TPC-DS dsdgen"
    else:
        raise AssertionError(f"unsupported generated family: {family}")

    target_catalog, target_columns, target_keys, _ = read_schema_authority(
        cli, schema_source, tables
    )
    try:
        cli.run(generator, call + "\nCHECKPOINT;", timeout=300.0)
    except BuildError as exc:
        raise BuildError(
            f"could not generate exact {family.upper()} SF0.01; DUCKDB_BIN must "
            f"include the bundled {generator_name} extension: {exc}"
        ) from exc

    data_catalog = validate_source_tables(
        cli.rows(generator, table_catalog_sql(tables)), tables
    )
    generated_columns = cli.rows(generator, column_catalog_sql(tables))
    if comparable_columns(target_columns) != comparable_columns(generated_columns):
        raise BuildError(
            f"generated {family.upper()} columns are incompatible with target schema"
        )
    generated_counts = parse_counts(cli.rows(generator, count_tables_sql(tables)))
    if generated_counts != expected_counts:
        raise BuildError(
            f"{family.upper()} cardinalities are not exact SF0.01: "
            f"expected {expected_counts}, got {generated_counts}"
        )

    clone_schema(cli, output, target_catalog, tables)
    insert_data(
        cli, generator, output, target_catalog, data_catalog, tables, row_cap=None
    )
    output_keys = validate_cloned_schema(
        cli, output, tables, target_columns, target_keys
    )
    output_counts = parse_counts(cli.rows(output, count_tables_sql(tables)))
    if output_counts != generated_counts:
        raise BuildError(
            f"generated {family.upper()} cardinality mismatch: "
            f"expected {generated_counts}, got {output_counts}"
        )
    validate_data_contents(
        cli, generator, output, target_catalog, data_catalog, tables, row_cap=None
    )
    return generated_counts, output_counts, output_keys


def top_level_words(sql: str) -> list[tuple[str, int, int]]:
    """Return unquoted depth-zero SQL words and their character spans."""
    words: list[tuple[str, int, int]] = []
    index = 0
    depth = 0
    state = "normal"
    block_depth = 0
    dollar_delimiter = ""
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if state == "normal":
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "-" and next_char == "-":
                state = "line_comment"
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                block_depth = 1
                index += 1
            elif char == "$":
                match = _DOLLAR_QUOTE.match(sql, index)
                if match:
                    dollar_delimiter = match.group(0)
                    state = "dollar"
                    index = match.end() - 1
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    raise BuildError("query has an unmatched closing parenthesis")
            elif depth == 0 and (char.isalpha() or char == "_"):
                end = index + 1
                while end < len(sql) and (
                    sql[end].isalnum() or sql[end] in "_$"
                ):
                    end += 1
                words.append((sql[index:end].casefold(), index, end))
                index = end - 1
        elif state == "single":
            if char == "'" and next_char == "'":
                index += 1
            elif char == "'":
                state = "normal"
        elif state == "double":
            if char == '"' and next_char == '"':
                index += 1
            elif char == '"':
                state = "normal"
        elif state == "line_comment":
            if char in "\r\n":
                state = "normal"
        elif state == "block_comment":
            if char == "/" and next_char == "*":
                block_depth += 1
                index += 1
            elif char == "*" and next_char == "/":
                block_depth -= 1
                index += 1
                if block_depth == 0:
                    state = "normal"
        elif state == "dollar":
            if sql.startswith(dollar_delimiter, index):
                index += len(dollar_delimiter) - 1
                dollar_delimiter = ""
                state = "normal"
        index += 1
    if depth != 0:
        raise BuildError("query has unbalanced parentheses")
    if state in ("single", "double", "block_comment", "dollar"):
        raise BuildError("query has an unterminated quoted value or comment")
    return words


def rewrite_witness_query(
    canonical_query: bytes, witness_rows: int
) -> tuple[str, list[tuple[str, str]]]:
    """Project alias rowids from one supported PGPlan corpus query."""
    query = canonical_query.decode("utf-8")
    aliases = _query_alias_occurrences(canonical_query)
    if not aliases:
        raise BuildError("witness query contains no base-table aliases")
    words = top_level_words(query)
    if not words or words[0][0] != "select":
        raise BuildError("witness rewriting requires a top-level SELECT")
    try:
        from_index = next(
            index for index, (word, _, _) in enumerate(words[1:], 1) if word == "from"
        )
    except StopIteration as exc:
        raise BuildError("witness rewriting requires a top-level FROM") from exc

    tail_start = len(query)
    tail_words = words[from_index + 1 :]
    for index, (word, start, _) in enumerate(tail_words):
        if word in ("union", "intersect", "except", "having"):
            raise BuildError(f"witness rewriting does not support top-level {word.upper()}")
        if word == "group":
            if index + 1 >= len(tail_words) or tail_words[index + 1][0] != "by":
                raise BuildError("malformed top-level GROUP clause")
            tail_start = min(tail_start, start)
        elif word in ("order", "limit", "offset", "fetch"):
            tail_start = min(tail_start, start)

    projections = []
    alias_relations: list[tuple[str, str]] = []
    for index, (alias, (relation, _)) in enumerate(aliases.items()):
        projections.append(
            f"{quote_identifier(alias)}.rowid AS "
            f"{quote_identifier(f'__pgplan_witness_{index}')}"
        )
        alias_relations.append((alias, relation.casefold()))
    select_end = words[0][2]
    from_start = words[from_index][1]
    rewritten = (
        query[:select_end]
        + "\n    "
        + ", ".join(projections)
        + "\n"
        + query[from_start:tail_start].rstrip()
        + f"\nLIMIT {witness_rows}"
    )
    return rewritten, alias_relations


def collect_target_witnesses(
    cli: DuckDBCLI,
    source: Path,
    query_dir: Path,
    tables: Sequence[str],
    witness_rows: int,
    query_timeout: float,
) -> tuple[dict[str, set[int]], dict[str, int]]:
    rowids = {table.casefold(): set() for table in tables}
    target_results: dict[str, int] = {}
    expected_tables = set(rowids)
    for path in query_files(query_dir):
        relative = str(path.relative_to(query_dir))
        try:
            canonical = canonicalize_query(path.read_bytes())
            query, aliases = rewrite_witness_query(canonical, witness_rows)
        except (OSError, PlanError, BuildError) as exc:
            raise BuildError(f"cannot construct target witness for {path}: {exc}") from exc
        relations = {relation for _, relation in aliases}
        unexpected = sorted(relations - expected_tables)
        if unexpected:
            raise BuildError(
                f"target witness {path} references tables outside family {unexpected}"
            )
        sql = (
            "SET disabled_optimizers = 'outer_yan';\n"
            "SET threads = 1;\n"
            + query
            + ";"
        )
        try:
            rows = cli.rows(source, sql, timeout=query_timeout)
        except BuildError as exc:
            raise BuildError(f"target witness extraction failed for {path}: {exc}") from exc
        if len(rows) > witness_rows:
            raise BuildError(f"target witness limit was not respected for {path}")
        target_results[relative] = len(rows)
        for row in rows:
            for index, (_, relation) in enumerate(aliases):
                value = row.get(f"__pgplan_witness_{index}")
                if value in (None, "", "NULL"):
                    continue
                try:
                    rowid = int(value, 10)
                except ValueError as exc:
                    raise BuildError(
                        f"target witness returned invalid rowid {value!r} for {path}"
                    ) from exc
                if rowid < 0:
                    raise BuildError(f"target witness returned a negative rowid for {path}")
                rowids[relation].add(rowid)
    return rowids, target_results


def add_target_witnesses(
    cli: DuckDBCLI,
    source: Path,
    output: Path,
    tables: Sequence[str],
    rowids: dict[str, set[int]],
) -> dict[str, int]:
    catalog = validate_source_tables(cli.rows(source, table_catalog_sql(tables)), tables)
    keyed_tables = {
        table for table, _, _ in parse_keys(cli.rows(source, key_catalog_sql(tables)))
    }
    before = parse_counts(cli.rows(output, count_tables_sql(tables)))
    alias = "pgplan_witness_source"
    statements = [
        f"ATTACH {quote_literal(str(source))} AS {quote_identifier(alias)} (READ_ONLY);",
        "BEGIN TRANSACTION;",
    ]
    for table in tables:
        selected = sorted(rowids[table.casefold()])
        if not selected:
            continue
        actual = quote_identifier(catalog[table.casefold()][0])
        identifiers = ", ".join(str(rowid) for rowid in selected)
        selected_rows = (
            f"SELECT * FROM {quote_identifier(alias)}.main.{actual} "
            f"WHERE rowid IN ({identifiers})"
        )
        if table.casefold() in keyed_tables:
            statements.append(
                f"INSERT OR IGNORE INTO main.{actual} {selected_rows} ORDER BY rowid;"
            )
        else:
            # Preserve the selected target multiset without inserting copies
            # that the generated/prefix base already contains.
            statements.append(
                f"INSERT INTO main.{actual} SELECT * FROM ("
                f"{selected_rows} EXCEPT ALL SELECT * FROM main.{actual}"
                ") AS missing_witness_rows;"
            )
    statements.extend(
        [
            "COMMIT;",
            f"DETACH {quote_identifier(alias)};",
            "ANALYZE;",
            "CHECKPOINT;",
        ]
    )
    cli.run(output, "\n".join(statements), timeout=300.0)
    after = parse_counts(cli.rows(output, count_tables_sql(tables)))
    return {table: after[table] - before[table] for table in before}


def query_files(query_dir: Path) -> list[Path]:
    if not query_dir.is_dir():
        raise BuildError(f"query directory does not exist: {query_dir}")
    paths = [path for path in query_dir.rglob("*.sql") if path.is_file()]
    paths.sort(key=lambda path: os.fsencode(str(path.relative_to(query_dir))))
    if not paths:
        raise BuildError(f"query directory contains no .sql files: {query_dir}")
    return paths


def validate_result_bounds(
    cli: DuckDBCLI,
    database: Path,
    query_dir: Path,
    max_result_rows: int,
    query_timeout: float,
    required_nonempty: set[str] | None = None,
) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    required_nonempty = required_nonempty or set()
    sentinel = max_result_rows + 1
    for path in query_files(query_dir):
        try:
            query = canonicalize_query(path.read_bytes()).decode("utf-8")
        except (OSError, UnicodeDecodeError, PlanError) as exc:
            raise BuildError(f"cannot validate query {path}: {exc}") from exc
        sql = f"""
            SET disabled_optimizers = 'outer_yan';
            SET threads = 1;
            SELECT count(*)::UBIGINT AS result_rows
            FROM (
                SELECT *
                FROM (
                    {query}
                ) AS pgplan_correctness_query
                LIMIT {sentinel}
            ) AS pgplan_bounded_result;
        """
        try:
            rows = cli.rows(database, sql, timeout=query_timeout)
        except BuildError as exc:
            raise BuildError(f"bounded result validation failed for {path}: {exc}") from exc
        if len(rows) != 1 or "result_rows" not in rows[0]:
            raise BuildError(f"invalid bounded count returned for {path}: {rows}")
        try:
            result_rows = int(rows[0]["result_rows"], 10)
        except ValueError as exc:
            raise BuildError(f"invalid bounded count returned for {path}: {rows[0]}") from exc
        if result_rows > max_result_rows:
            raise BuildError(
                f"{path} exceeds --max-result-rows={max_result_rows}; "
                f"bounded validation observed at least {sentinel} rows"
            )
        relative = str(path.relative_to(query_dir))
        if relative in required_nonempty and result_rows == 0:
            raise BuildError(
                f"{path} is nonempty on the target database but empty after witness enrichment"
            )
        results.append((relative, result_rows))
    return results


def write_manifest(
    path: Path,
    *,
    family: str,
    sample_label: str,
    source: Path | None,
    row_cap: int | None,
    source_counts: dict[str, int],
    output_counts: dict[str, int],
    key_count: int,
    query_results: Sequence[tuple[str, int]],
    max_result_rows: int,
    witness_rows_added: dict[str, int],
    target_witness_results: dict[str, int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "record_type",
                "family",
                "object",
                "sample_label",
                "row_cap",
                "source_rows",
                "loaded_rows",
                "result_rows",
                "max_result_rows",
                "pk_unique_constraints",
                "source_db",
                "sampling",
                "witness_rows_added",
                "target_witness_rows",
            ]
        )
        sampling = {
            "tpch": "tpch-dbgen-sf0.01",
            "tpcds": "tpcds-dsdgen-sf0.01+target-rowid-witness",
            "graph": "order-by-rowid-prefix",
            "job": "order-by-rowid-prefix+target-rowid-witness",
        }[family]
        source_value = "" if source is None else str(source)
        for table in FAMILY_TABLES[family]:
            folded = table.casefold()
            writer.writerow(
                [
                    "table",
                    family,
                    folded,
                    sample_label,
                    "" if row_cap is None else row_cap,
                    source_counts[folded],
                    output_counts[folded],
                    "",
                    "",
                    key_count,
                    source_value,
                    sampling,
                    witness_rows_added.get(folded, 0),
                    "",
                ]
            )
        for query, result_rows in query_results:
            writer.writerow(
                [
                    "query",
                    family,
                    query,
                    sample_label,
                    "" if row_cap is None else row_cap,
                    "",
                    "",
                    result_rows,
                    max_result_rows,
                    key_count,
                    source_value,
                    sampling,
                    "",
                    target_witness_results.get(query, 0),
                ]
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a bounded, size-validated DuckDB execution database "
            "for PGPlan correctness comparisons."
        )
    )
    parser.add_argument("--family", required=True, choices=sorted(FAMILY_TABLES))
    parser.add_argument(
        "--source-db",
        required=True,
        help="target DuckDB database whose exact table DDL and keys are cloned",
    )
    parser.add_argument("--out", required=True, help="output DuckDB database path")
    parser.add_argument(
        "--rows",
        type=positive_int,
        default=None,
        help=(
            "physical-row prefix per graph/JOB table (defaults: graph=500, "
            "job=1000; ignored for generated TPC-H/TPC-DS)"
        ),
    )
    parser.add_argument(
        "--manifest",
        help="output TSV manifest (default: OUT.manifest.tsv)",
    )
    parser.add_argument(
        "--query-dir",
        help="queries to bound-check (default: auto_test/outerjoin_benchmark/benchmark/FAMILY)",
    )
    parser.add_argument(
        "--max-result-rows",
        type=positive_int,
        default=positive_int(
            os.environ.get(
                "PGPLAN_CORRECTNESS_MAX_RESULT_ROWS", str(DEFAULT_MAX_RESULT_ROWS)
            )
        ),
        help=f"maximum result rows for every query (default: {DEFAULT_MAX_RESULT_ROWS})",
    )
    parser.add_argument(
        "--query-timeout",
        type=positive_float,
        default=positive_float(
            os.environ.get(
                "PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS", str(DEFAULT_QUERY_TIMEOUT)
            )
        ),
        metavar="SECS",
        help=f"per-query bounded-count timeout (default: {DEFAULT_QUERY_TIMEOUT:g})",
    )
    parser.add_argument(
        "--witness-rows",
        type=positive_int,
        default=DEFAULT_WITNESS_ROWS,
        help=(
            "target witness rows per TPC-DS/JOB query "
            f"(default: {DEFAULT_WITNESS_ROWS})"
        ),
    )
    parser.add_argument(
        "--duckdb-bin",
        default=default_duckdb_binary(),
        help="DuckDB CLI path (default: DUCKDB_BIN or this checkout's build)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="atomically replace an existing output database and manifest",
    )
    return parser


def validate_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    output = Path(args.out).expanduser().resolve()
    if output.exists() and output.is_dir():
        raise BuildError(f"output path is a directory: {output}")
    manifest = (
        Path(args.manifest).expanduser().resolve()
        if args.manifest
        else output.with_name(output.name + ".manifest.tsv")
    )
    query_dir = (
        Path(args.query_dir).expanduser().resolve()
        if args.query_dir
        else REPO_ROOT / "auto_test" / "outerjoin_benchmark" / "benchmark" / args.family
    )

    source = Path(args.source_db).expanduser().resolve()
    if not source.is_file():
        raise BuildError(f"source DuckDB database does not exist: {source}")
    if source == output:
        raise BuildError("--source-db and --out must be different paths")
    if manifest == output:
        raise BuildError("--manifest and --out must be different paths")
    if manifest == source:
        raise BuildError("--manifest and --source-db must be different paths")

    if output.exists() and not args.force:
        raise BuildError(f"output already exists; pass --force to replace it: {output}")
    if manifest.exists() and not args.force:
        raise BuildError(f"manifest already exists; pass --force to replace it: {manifest}")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    return source, output, manifest, query_dir


def publish_file(staged: Path, destination: Path, force: bool) -> None:
    if destination.exists() and not force:
        raise BuildError(f"destination appeared during build: {destination}")
    os.replace(staged, destination)


def resolve_row_cap(args: argparse.Namespace) -> int | None:
    if args.family in ("tpch", "tpcds"):
        return None
    if args.rows is not None:
        return args.rows
    configured = os.environ.get("PGPLAN_CORRECTNESS_ROWS")
    if configured is not None:
        try:
            return positive_int(configured)
        except argparse.ArgumentTypeError as exc:
            raise BuildError("PGPLAN_CORRECTNESS_ROWS must be a positive integer") from exc
    return DEFAULT_ROWS[args.family]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_result_rows >= (1 << 63) - 1:
        raise BuildError("--max-result-rows is too large")
    executable = resolve_executable(args.duckdb_bin)
    source, output, manifest, query_dir = validate_paths(args)
    cli = DuckDBCLI(executable)
    tables = FAMILY_TABLES[args.family]
    row_cap = resolve_row_cap(args)

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.building.", dir=str(output.parent))
    )
    staged_db = temporary / "database.duckdb"
    manifest_fd, manifest_name = tempfile.mkstemp(
        prefix=f".{manifest.name}.building.", dir=str(manifest.parent)
    )
    os.close(manifest_fd)
    staged_manifest = Path(manifest_name)
    try:
        if args.family in ("tpch", "tpcds"):
            generator = temporary / "generated.duckdb"
            source_counts, output_counts, keys = build_generated_sf001(
                cli, source, generator, staged_db, tables, args.family
            )
            sample_label = (
                "tpch-sf0.01"
                if args.family == "tpch"
                else "tpcds-dsdgen-sf0.01"
            )
        else:
            assert row_cap is not None
            source_counts, output_counts, keys = build_prefix_sample(
                cli, source, staged_db, tables, row_cap
            )
            sample_label = f"{args.family}-duckdb-sample-{row_cap}"

        witness_rows_added = {table.casefold(): 0 for table in tables}
        target_witness_results: dict[str, int] = {}
        if args.family in ("tpcds", "job"):
            witness_rowids, target_witness_results = collect_target_witnesses(
                cli,
                source,
                query_dir,
                tables,
                args.witness_rows,
                args.query_timeout,
            )
            witness_rows_added = add_target_witnesses(
                cli, source, staged_db, tables, witness_rowids
            )
            output_counts = parse_counts(
                cli.rows(staged_db, count_tables_sql(tables))
            )

        query_results = validate_result_bounds(
            cli,
            staged_db,
            query_dir,
            args.max_result_rows,
            args.query_timeout,
            {
                query
                for query, count in target_witness_results.items()
                if count > 0
            },
        )
        write_manifest(
            staged_manifest,
            family=args.family,
            sample_label=sample_label,
            source=source,
            row_cap=row_cap,
            source_counts=source_counts,
            output_counts=output_counts,
            key_count=len(keys),
            query_results=query_results,
            max_result_rows=args.max_result_rows,
            witness_rows_added=witness_rows_added,
            target_witness_results=target_witness_results,
        )

        # A stale WAL from an explicitly replaced database must not be paired
        # with the new file.  Closed successful builds have no staged WAL.
        output_wal = output.with_name(output.name + ".wal")
        if output_wal.exists():
            if not args.force:
                raise BuildError(f"output WAL already exists: {output_wal}")
            output_wal.unlink()
        publish_file(staged_db, output, args.force)
        publish_file(staged_manifest, manifest, args.force)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        try:
            staged_manifest.unlink()
        except FileNotFoundError:
            pass

    maximum = max((count for _, count in query_results), default=0)
    diagnostic = {
        "database": str(output),
        "family": args.family,
        "manifest": str(manifest),
        "max_observed_result_rows": maximum,
        "max_result_rows": args.max_result_rows,
        "pk_unique_constraints": len(keys),
        "queries": len(query_results),
        "sample_label": sample_label,
        "tables": len(tables),
        "target_nonempty_queries": sum(
            count > 0 for count in target_witness_results.values()
        ),
        "witness_rows_added": sum(witness_rows_added.values()),
    }
    print("[PGPLAN_CORRECTNESS_DB] " + json.dumps(diagnostic, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
