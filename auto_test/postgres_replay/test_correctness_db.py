#!/usr/bin/env python3
"""Focused tests for the portable PGPlan correctness database builder."""

from __future__ import annotations

import ast
import csv
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
BUILDER = SCRIPT_DIR / "prepare_correctness_db.py"
RUNTIME_PYTHON_SCRIPTS = tuple(
    path
    for path in sorted(SCRIPT_DIR.glob("*.py"))
    if not path.name.startswith("test_")
)
sys.path.insert(0, str(SCRIPT_DIR))
import prepare_correctness_db as correctness_builder  # noqa: E402


def find_duckdb() -> Path | None:
    configured = os.environ.get("DUCKDB_BIN")
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            REPO_ROOT / "build" / "release" / "duckdb",
            REPO_ROOT / "build" / "debug" / "duckdb",
        ]
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    return None


class PythonCompatibilityTest(unittest.TestCase):
    def test_runtime_scripts_parse_with_python_37_grammar(self) -> None:
        for script in RUNTIME_PYTHON_SCRIPTS:
            with self.subTest(script=script.name):
                source = script.read_text(encoding="utf-8")
                if sys.version_info >= (3, 11):
                    ast.parse(
                        source,
                        filename=str(script),
                        feature_version=(3, 7),
                    )
                elif sys.version_info >= (3, 8):
                    ast.parse(source, filename=str(script), feature_version=7)
                else:
                    # Running under 3.7 already enforces the desired grammar.
                    ast.parse(source, filename=str(script))

    def test_runtime_scripts_avoid_python_38_path_unlink_keyword(self) -> None:
        incompatible_calls = []
        for script in RUNTIME_PYTHON_SCRIPTS:
            source = script.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(script))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if (
                    not isinstance(node.func, ast.Attribute)
                    or node.func.attr != "unlink"
                ):
                    continue
                if any(keyword.arg == "missing_ok" for keyword in node.keywords):
                    incompatible_calls.append((script.name, node.lineno))
        self.assertEqual(
            incompatible_calls,
            [],
            "Path.unlink(missing_ok=...) requires Python 3.8; "
            f"incompatible call(s): {incompatible_calls}",
        )


class CorrectnessDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.duckdb = find_duckdb()
        if cls.duckdb is None:
            raise unittest.SkipTest("a built DuckDB CLI is required")

    def run_duckdb(self, database: Path, sql: str) -> list[dict[str, str]]:
        result = subprocess.run(
            [
                str(self.duckdb),
                str(database),
                "-no-init",
                "-bail",
                "-csv",
                "-header",
                "-c",
                sql,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return list(csv.DictReader(io.StringIO(result.stdout)))

    def run_builder(
        self,
        family: str,
        source: Path,
        output: Path,
        query_dir: Path,
        *extra: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--family",
                family,
                "--source-db",
                str(source),
                "--out",
                str(output),
                "--query-dir",
                str(query_dir),
                "--duckdb-bin",
                str(self.duckdb),
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def create_graph_source(self, path: Path) -> None:
        statements = []
        for index in range(1, 11):
            statements.extend(
                [
                    f"CREATE TABLE R{index}("
                    "src BIGINT NOT NULL, dst BIGINT, UNIQUE(src, dst));",
                    f"INSERT INTO R{index} VALUES (1, 2), (2, 3), (3, 4), (4, 5);",
                ]
            )
        self.run_duckdb(path, "\n".join(statements))

    def test_witness_rewriter_projects_rowids_and_removes_root_group(self) -> None:
        query = (
            b"SELECT i_category, count(ss_item_sk) AS sold_cnt\n"
            b"FROM store_sales LEFT JOIN item ON ss_item_sk=i_item_sk\n"
            b"WHERE ss_quantity > 0 GROUP BY i_category"
        )
        rewritten, aliases = correctness_builder.rewrite_witness_query(query, 1)
        self.assertEqual(aliases, [("store_sales", "store_sales"), ("item", "item")])
        self.assertIn('"store_sales".rowid', rewritten)
        self.assertIn('"item".rowid', rewritten)
        self.assertNotIn("GROUP BY", rewritten.upper())
        self.assertTrue(rewritten.endswith("LIMIT 1"))

    def test_prefix_sample_preserves_schema_keys_and_exact_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.duckdb"
            output = root / "correctness.duckdb"
            manifest = root / "manifest.tsv"
            queries = root / "queries"
            queries.mkdir()
            (queries / "one.sql").write_text(
                "SELECT * FROM R1 LEFT JOIN R2 ON R1.dst=R2.src;\n",
                encoding="utf-8",
            )
            self.create_graph_source(source)

            result = self.run_builder(
                "graph",
                source,
                output,
                queries,
                "--rows",
                "2",
                "--max-result-rows",
                "10",
                "--manifest",
                str(manifest),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[PGPLAN_CORRECTNESS_DB]", result.stdout)

            rows = self.run_duckdb(
                output,
                "SELECT (SELECT count(*) FROM R1) AS r1_rows, "
                "(SELECT count(*) FROM R1 WHERE src=1 AND dst=2) AS first_row, "
                "(SELECT count(*) FROM duckdb_constraints() "
                " WHERE constraint_type='UNIQUE') AS unique_keys;",
            )
            self.assertEqual(
                rows,
                [{"r1_rows": "2", "first_row": "1", "unique_keys": "10"}],
            )
            with manifest.open(newline="", encoding="utf-8") as source_file:
                records = list(csv.DictReader(source_file, delimiter="\t"))
            table = next(record for record in records if record["object"] == "r1")
            query = next(record for record in records if record["record_type"] == "query")
            self.assertEqual(table["source_rows"], "4")
            self.assertEqual(table["loaded_rows"], "2")
            self.assertEqual(table["sampling"], "order-by-rowid-prefix")
            self.assertEqual(query["result_rows"], "2")

    def test_bound_failure_does_not_publish_database_or_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.duckdb"
            output = root / "too_large.duckdb"
            manifest = Path(str(output) + ".manifest.tsv")
            queries = root / "queries"
            queries.mkdir()
            (queries / "too_large.sql").write_text(
                "SELECT * FROM R1 CROSS JOIN R2;\n", encoding="utf-8"
            )
            self.create_graph_source(source)

            result = self.run_builder(
                "graph",
                source,
                output,
                queries,
                "--rows",
                "3",
                "--max-result-rows",
                "8",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("observed at least 9 rows", result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse(manifest.exists())

    def test_generated_suites_clone_target_keys(self) -> None:
        cases = (
            (
                "tpch",
                "CALL dbgen(sf=0.01); "
                "ALTER TABLE region ADD PRIMARY KEY (r_regionkey);",
                "SELECT * FROM region;",
                "region",
                "5",
                "tpch-dbgen-sf0.01",
            ),
            (
                "tpcds",
                "CALL dsdgen(sf=0.01); "
                "ALTER TABLE store ADD PRIMARY KEY (s_store_sk); "
                "UPDATE store_sales SET ss_quantity=9999 WHERE rowid=0;",
                "SELECT * FROM store_sales WHERE ss_quantity=9999;",
                "store_sales",
                "28811",
                "tpcds-dsdgen-sf0.01",
            ),
        )
        for family, setup, query, table, expected_rows, strategy in cases:
            with self.subTest(family=family), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "target_schema.duckdb"
                output = root / "correctness.duckdb"
                manifest = root / "manifest.tsv"
                queries = root / "queries"
                queries.mkdir()
                (queries / "bounded.sql").write_text(query + "\n", encoding="utf-8")
                if family == "tpcds":
                    (queries / "already_present.sql").write_text(
                        "SELECT * FROM store_sales WHERE rowid=1;\n",
                        encoding="utf-8",
                    )
                self.run_duckdb(source, setup)

                result = self.run_builder(
                    family,
                    source,
                    output,
                    queries,
                    "--max-result-rows",
                    "10",
                    "--manifest",
                    str(manifest),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                rows = self.run_duckdb(
                    output,
                    f"SELECT (SELECT count(*) FROM {table}) AS table_rows, "
                    "(SELECT count(*) FROM duckdb_constraints() "
                    " WHERE constraint_type='PRIMARY KEY') AS primary_keys;",
                )
                self.assertEqual(rows[0]["table_rows"], expected_rows)
                self.assertEqual(rows[0]["primary_keys"], "1")
                manifest_text = manifest.read_text(encoding="utf-8")
                self.assertIn(strategy, manifest_text)
                if family == "tpcds":
                    self.assertIn("target-rowid-witness", manifest_text)
                    with manifest.open(newline="", encoding="utf-8") as manifest_file:
                        records = list(csv.DictReader(manifest_file, delimiter="\t"))
                    store_sales = next(
                        record
                        for record in records
                        if record["record_type"] == "table"
                        and record["object"] == "store_sales"
                    )
                    witness_query = next(
                        record
                        for record in records
                        if record["record_type"] == "query"
                    )
                    self.assertEqual(store_sales["loaded_rows"], "28811")
                    self.assertEqual(store_sales["witness_rows_added"], "1")
                    self.assertEqual(witness_query["target_witness_rows"], "1")


if __name__ == "__main__":
    unittest.main()
