"""Exercise the actual libpq client against an isolated disposable PG cluster."""
import os
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from run import Postgres


@unittest.skipUnless(os.environ.get("PGPLAN_TEST_PG_BIN_DIR"), "set PGPLAN_TEST_PG_BIN_DIR for libpq integration tests")
class StreamClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="pg-stream-test-")
        args = SimpleNamespace(pg_bin_dir=Path(os.environ["PGPLAN_TEST_PG_BIN_DIR"]).resolve())
        cls.pg = Postgres(args, Path(cls.directory.name))
        try:
            cls.pg.__enter__()
        except BaseException:
            cls.directory.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            cls.pg.close()
        finally:
            cls.directory.cleanup()

    def stream(self, sql, jsonl=False):
        pg = self.pg
        command = [pg.bin / "pg_bare_query", pg.socket.name, "55439", "oy_study", "postgres", "4"]
        if jsonl:
            command.append('jsonl')
        return subprocess.run(command,
                              input=sql, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)

    def test_jsonl_preserves_text_null_and_embedded_record_separators(self):
        result = self.stream("SELECT E'line\\nquote\"\\t\\\\end'::text, NULL::text, 'NULL'::text, -123::bigint;", True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(json.loads(result.stdout), ['line\nquote"\t\\end', None, 'NULL', '-123'])
        self.assertIn('rows=1 columns=4 completed=1', result.stderr)

    def test_jsonl_rejects_unsupported_numeric_types(self):
        result = self.stream('SELECT 1.25::numeric, 2, 3, 4;', True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('completed=1', result.stderr)

    def test_same_bare_select_matches_psql_with_duplicates_nulls_and_negatives(self):
        sql = ("SET statement_timeout=10000; SET application_name='stream_test'; "
               "SELECT CASE WHEN i%7=0 THEN NULL ELSE i%10 END, i%5, -(i%3), NULL::bigint "
               "FROM generate_series(1,20000) AS t(i);")
        pg = self.pg
        expected = subprocess.run([pg.bin / "psql", "-X", "-w", "-h", pg.socket.name, "-p", "55439",
                                   "-U", "oy_study", "-d", "postgres", "-qAt", "--csv", "-P", "null=NULL",
                                   "-v", "ON_ERROR_STOP=1"], input=sql, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=20)
        result = self.stream(sql)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected.stdout)
        self.assertIn("rows=20000 columns=4 completed=1", result.stderr)

    def test_empty_select_is_a_successful_complete_result(self):
        result = self.stream("SELECT 1,2,3,NULL::int WHERE false;")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("rows=0 columns=4 completed=1", result.stderr)

    def test_error_after_partial_rows_never_reports_success(self):
        result = self.stream("SELECT i,1,2,10/(20000-i) FROM generate_series(1,20000) AS t(i);")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout)
        self.assertIn("division by zero", result.stderr)
        self.assertNotIn("completed=1", result.stderr)

    def test_unexpected_fields_or_extra_select_are_rejected(self):
        for sql in ("SELECT 1,2,3;", "SELECT 1,2,3,'a,b';", "SELECT 1,2,3,4; SELECT 1,2,3,4;"):
            with self.subTest(sql=sql):
                result = self.stream(sql)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("completed=1", result.stderr)


if __name__ == "__main__":
    unittest.main()
