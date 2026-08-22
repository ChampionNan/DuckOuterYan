#!/usr/bin/env python3

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
MAKE_PLAN = SCRIPT_DIR / "make_plan.sh"
FIXTURE = SCRIPT_DIR / "fixtures" / "hash_left.json"


FAKE_PSQL = r"""#!/usr/bin/env python3
import os
import pathlib
import sys

command = next((arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--command=")), None)
sql_file = next((arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--file=")), None)
if command and "server_version_num" in command:
    mutate = os.environ.get("FAKE_MUTATE_QUERY")
    if mutate:
        pathlib.Path(mutate).write_text("SELECT 2;\n", encoding="utf-8")
    print(os.environ.get("FAKE_PG_VERSION", "160002"))
elif command and "FROM pg_settings" in command:
    print(os.environ.get("FAKE_NONDEFAULT_SETTINGS", ""), end="")
elif sql_file:
    capture = pathlib.Path(sql_file).read_text(encoding="utf-8")
    assert "EXPLAIN (FORMAT JSON, VERBOSE, COSTS TRUE, SETTINGS TRUE)" in capture
    assert "EXPLAIN (ANALYZE" not in capture
    assert capture.startswith("BEGIN READ ONLY;")
    if os.environ.get("FAKE_CAPTURE_TIMEOUT"):
        assert "SET LOCAL statement_timeout = '7s';" in capture
        print(
            "ERROR:  57014: canceling statement due to statement timeout",
            file=sys.stderr,
        )
        raise SystemExit(3)
    if os.environ.get("FAKE_CAPTURE_ERROR"):
        print("ERROR:  XX000: unrelated capture failure", file=sys.stderr)
        raise SystemExit(9)
    sys.stdout.write(pathlib.Path(os.environ["FAKE_EXPLAIN_JSON"]).read_text(encoding="utf-8"))
else:
    raise SystemExit("unexpected fake psql invocation: " + repr(sys.argv))
"""


class MakePlanIntegrationTest(unittest.TestCase):
    def run_capture(self, version="160002", nondefaults="", mutate_query=False,
                    out_is_query=False, capture_timeout=False,
                    capture_error=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "path with spaces"
        root.mkdir()
        fake_psql = root / "psql"
        fake_psql.write_text(FAKE_PSQL, encoding="utf-8")
        fake_psql.chmod(0o755)
        query = root / "query.sql"
        query.write_bytes(
            b"\r\n-- benchmark provenance;\r\n"
            b"/* outer /* nested */ comment */\r\n SELECT 1; \r\n"
        )
        artifact = query if out_is_query else root / "plan.json"
        env = os.environ.copy()
        env.update(
            {
                "PSQL_BIN": str(fake_psql),
                "PYTHON_BIN": sys.executable,
                "FAKE_EXPLAIN_JSON": str(FIXTURE),
                "FAKE_PG_VERSION": version,
                "FAKE_NONDEFAULT_SETTINGS": nondefaults,
            }
        )
        if mutate_query:
            env["FAKE_MUTATE_QUERY"] = str(query)
        if capture_timeout:
            env["FAKE_CAPTURE_TIMEOUT"] = "1"
            env["PGPLAN_CAPTURE_TIMEOUT_SECS"] = "7"
        if capture_error:
            env["FAKE_CAPTURE_ERROR"] = "1"
        result = subprocess.run(
            [
                "bash",
                str(MAKE_PLAN),
                "--pg-dsn",
                "host=fake dbname=fake",
                "--query",
                str(query),
                "--expected-pg-version",
                "160002",
                "--out",
                str(artifact),
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        return result, artifact

    def test_writes_normalized_artifact_through_psql_boundary(self):
        result, artifact_path = self.run_capture()
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(artifact["format"], "duckyan.pg_join_tree.v1")
        self.assertEqual(artifact["tree"]["join_type"], "left")
        self.assertEqual(
            artifact["query_sha256"], hashlib.sha256(b"SELECT 1").hexdigest()
        )

    def test_server_version_mismatch_fails_without_artifact(self):
        result, artifact_path = self.run_capture(version="160003")
        self.assertEqual(result.returncode, 2)
        self.assertIn("server_version_num mismatch", result.stderr)
        self.assertFalse(artifact_path.exists())

    def test_nondefault_query_tuning_setting_fails(self):
        result, artifact_path = self.run_capture(
            nondefaults="enable_hashjoin=off (compiled default=on)\n"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("not at compiled defaults", result.stderr)
        self.assertFalse(artifact_path.exists())

    def test_query_is_snapshotted_before_psql_can_observe_an_edit(self):
        result, artifact_path = self.run_capture(mutate_query=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(
            artifact["query_sha256"], hashlib.sha256(b"SELECT 1").hexdigest()
        )

    def test_refuses_to_overwrite_the_input_query(self):
        result, query_path = self.run_capture(out_is_query=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not overwrite", result.stderr)
        self.assertEqual(
            query_path.read_bytes(),
            b"\r\n-- benchmark provenance;\r\n"
            b"/* outer /* nested */ comment */\r\n SELECT 1; \r\n",
        )

    def test_plain_explain_timeout_writes_no_artifact_and_returns_124(self):
        result, artifact_path = self.run_capture(capture_timeout=True)
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertIn("SKIP capture_timeout seconds=7", result.stderr)
        self.assertNotIn("EXPLAIN ANALYZE", result.stderr)
        self.assertFalse(artifact_path.exists())

    def test_non_timeout_capture_error_remains_failure(self):
        result, artifact_path = self.run_capture(capture_error=True)
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertIn("XX000: unrelated capture failure", result.stderr)
        self.assertNotIn("SKIP capture_timeout", result.stderr)
        self.assertFalse(artifact_path.exists())


if __name__ == "__main__":
    unittest.main()
