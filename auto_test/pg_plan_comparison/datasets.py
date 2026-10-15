"""Reuse benchmark data; export only needed tables, with no row sampling/generation."""

import csv
import io
import json
import re
from pathlib import Path
import subprocess

from plans import sha256


def ident(value):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
        raise ValueError("unsupported benchmark identifier: " + value)
    return '"' + value + '"'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def fingerprint(path):
    files = {}
    for file in (path, Path(str(path) + ".wal")):
        if file.exists():
            stat = file.stat()
            files[str(file)] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return files


def assert_unchanged(data):
    if fingerprint(Path(data["source_db"])) != data["source_files"]:
        raise ValueError("source DuckDB database changed during experiment: " + data["source_db"])


def pg_type(duck_type):
    types = {"TINYINT": "SMALLINT", "SMALLINT": "SMALLINT", "INTEGER": "INTEGER", "BIGINT": "BIGINT",
             "UTINYINT": "SMALLINT", "USMALLINT": "INTEGER", "UINTEGER": "BIGINT", "UBIGINT": "NUMERIC(20,0)",
             "HUGEINT": "NUMERIC(39,0)", "UHUGEINT": "NUMERIC(39,0)",
             "VARCHAR": "TEXT", "BOOLEAN": "BOOLEAN", "FLOAT": "REAL", "DOUBLE": "DOUBLE PRECISION",
             "DATE": "DATE", "TIMESTAMP": "TIMESTAMP", "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ"}
    if duck_type in types:
        return types[duck_type]
    if re.fullmatch(r"DECIMAL\(\d+,\d+\)", duck_type):
        return duck_type
    raise ValueError("unsupported benchmark column type: " + duck_type)


def source_database(args, duck, spec, out):
    source = getattr(args, spec["family"] + "_db")
    if source.is_file():
        return source
    if spec["family"] != "job":
        raise ValueError(f"missing {spec['family']} database: {source}; provide the existing --{spec['family']}-db. "
                         "The experiment never runs dbgen/dsdgen.")
    cache = args.job_parquet_dir
    cache.mkdir(parents=True, exist_ok=True)
    sources = []
    for table in spec["tables"]:
        file = cache / ("job_" + table + ".parquet")
        url = "https://github.com/duckdb/duckdb-data/releases/download/v1.0/" + file.name
        if not file.is_file():
            if not args.download_missing_job:
                raise ValueError(f"missing JOB database and {file}; provide --job-db, cached --job-parquet-dir, "
                                 "or explicitly use --download-missing-job")
            temporary = file.with_suffix(".parquet.partial")
            subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--proto", "=https",
                            "--output", str(temporary), url], check=True, timeout=args.timeout)
            temporary.replace(file)
        sources.append({"table": table, "path": str(file), "url": url, "sha256": sha256(file)})
    source = out / "job_selected_tables.duckdb"
    if source.exists():
        raise ValueError("refusing to overwrite " + str(source))
    sql = "SET disabled_optimizers TO 'outer_yan';\n"
    for entry in sources:
        table = ident(entry["table"])
        sql += f"CREATE TABLE {table} AS SELECT * FROM read_parquet({literal(entry['path'])});\n"
        # Match build_db.sh's authentic JOB schema: id is the source surrogate PK.
        sql += f"ALTER TABLE {table} ADD PRIMARY KEY (id);\n"
    duck.run(source, sql + "CHECKPOINT;\n", out / "load_job_parquet.log", readonly=False,
             timeout=args.load_timeout)
    (out / "job_downloads.json").write_text(json.dumps(sources, indent=2) + "\n")
    return source


def export_tables(args, duck, spec, directory, source):
    """DuckDB executes against `source` itself, preserving its schema/statistics."""
    data = {"kind": "existing_benchmark_full_tables", "family": spec["family"],
            "source_db": str(source), "source_files": fingerprint(source),
            "source_benchmark": spec["source_benchmark"], "derivation": spec["derivation"],
            "table_row_policy": "all rows and columns; no sampling, filter, LIMIT or data generation",
            "tables": []}

    def records(sql, name):
        text = duck.run(source, ".mode csv\n.headers on\n" + sql + ";\n", directory / (name + ".log"))
        return list(csv.DictReader(io.StringIO(text)))

    for table in spec["tables"]:
        cols = records("SELECT column_name,data_type,is_nullable FROM information_schema.columns "
                       "WHERE table_schema='main' AND table_name=" + literal(table) + " ORDER BY ordinal_position",
                       table + ".columns")
        if not cols:
            raise ValueError("required original benchmark table missing: " + table)
        constraints = records("SELECT constraint_type, array_to_string(constraint_column_names, ',') AS columns "
                              "FROM duckdb_constraints() WHERE schema_name='main' AND table_name=" + literal(table),
                              table + ".constraints")
        definition = [ident(c["column_name"]) + " " + pg_type(c["data_type"]) +
                      (" NOT NULL" if c["is_nullable"] == "NO" else "") for c in cols]
        keys = []
        for constraint in constraints:
            kind = constraint["constraint_type"]
            if kind in {"PRIMARY KEY", "UNIQUE"}:
                keys.append({"kind": kind, "columns": constraint["columns"].split(",")})
            elif kind != "NOT NULL":
                raise ValueError(f"unsupported source constraint {kind} on {table}; refusing silent schema drift")
        for key in keys:
            definition.append(key["kind"] + " (" + ",".join(ident(c) for c in key["columns"]) + ")")
        count = int(records("SELECT count(*) AS n FROM " + ident(table), table + ".count")[0]["n"])
        file = directory / (table + ".csv")
        print(f"  export {spec['family']}.{table}: {count:,} original rows", flush=True)
        # COPY is data transfer only. It never encloses an experiment query.
        duck.run(source, f"COPY {ident(table)} TO {literal(file)} (FORMAT CSV, HEADER, NULL '\\N');\n",
                 directory / (table + ".export.log"), timeout=args.load_timeout)
        data["tables"].append({"relation": table, "rows": count, "columns": cols, "keys": keys,
                               "csv_sha256": sha256(file), "csv_bytes": file.stat().st_size,
                               "pg_ddl": "CREATE TABLE " + ident(table) + " (" + ", ".join(definition) + ");"})
    assert_unchanged(data)
    return data


def import_tables(pg, spec, directory, data):
    schema = "pgplan_" + spec["family"]
    sql = "CREATE SCHEMA " + ident(schema) + ";\n" + pg.setup(spec["family"], loading=True)
    for table in data["tables"]:
        name = table["relation"]
        sql += "\\echo Loading " + schema + "." + name + "\n"
        sql += table["pg_ddl"] + "\n"
        sql += (f"\\copy {ident(name)} FROM '{directory / (name + '.csv')}' "
                "WITH (FORMAT csv, HEADER true, NULL '\\N')\n" + f"ANALYZE {ident(name)};\n")
    (directory / "load_pg.sql").write_text(sql)
    pg.run(sql, directory / "load_pg.log", output=directory / "load_pg.stdout",
           timeout=pg.args.load_timeout)
    for table in data["tables"]:
        count = int(pg.run(pg.setup(spec["family"], loading=True) +
                           "SELECT count(*) FROM " + ident(table["relation"]) + ";\n",
                           directory / (table["relation"] + ".pg_count.log"), timeout=pg.args.load_timeout).strip())
        if count != table["rows"]:
            raise ValueError("PG row count differs from source table: " + table["relation"])
