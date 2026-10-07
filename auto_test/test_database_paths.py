"""Scale-qualified path resolution; no database generation or file mutation."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from database_paths import database_path


SCRIPT_DIR = Path(__file__).resolve().parent
FAMILIES = ("graph", "tpch", "tpcds", "job")


class DatabasePathsTest(unittest.TestCase):
    def shell_paths(self, root, overrides):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("OY_", "TPCH_", "TPCDS_", "GRAPH_", "JOB_"))}
        env.update(overrides)
        env["OY_REPO_ROOT"] = str(root)
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; printf "%s\\n" "$GRAPH_DB" "$TPCH_DB" "$TPCDS_DB" "$JOB_DB"',
             "database-path-test", str(SCRIPT_DIR / "configs.sh")],
            env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return dict(zip(FAMILIES, map(Path, result.stdout.splitlines())))

    def test_shell_python_defaults_agree(self):
        root = Path("/tmp/repository with spaces")
        for overrides in ({}, {"TPCH_SF": "100", "TPCDS_SF": "100"},
                          {"TPCH_SF": "1", "TPCDS_SF": "50"},
                          {"TPCH_SF": "0.1", "TPCDS_SF": "1"},
                          {"TPCH_SF": "", "TPCDS_DB": ""}):
            with self.subTest(overrides=overrides):
                expected = {family: database_path(family, root, overrides) for family in FAMILIES}
                self.assertEqual(expected, self.shell_paths(root, overrides))
        self.assertEqual(database_path("tpch", root, {}), root / "tpch_50.duckdb")
        self.assertEqual(database_path("tpcds", root, {"TPCDS_SF": "100"}),
                         root / "tpcds_100.duckdb")

    def test_explicit_paths_override_scale(self):
        root = Path("/tmp/repository")
        overrides = {"TPCH_SF": "100", "TPCDS_SF": "100",
                     "TPCH_DB": "/kept tpch/tpch_db", "TPCDS_DB": "existing/tpcds_sf50.duckdb",
                     "GRAPH_DB": "/graph/bitcoin", "JOB_DB": "/job/imdb"}
        actual = self.shell_paths(root, overrides)
        for family in FAMILIES:
            self.assertEqual(actual[family], Path(overrides[family.upper() + "_DB"]))
            self.assertEqual(actual[family], database_path(family, root, overrides))

    def test_legacy_files_are_not_selected_or_modified(self):
        with tempfile.TemporaryDirectory(prefix="outeryan-database-paths-") as directory:
            root = Path(directory)
            old_files = {root / "tpch_db": b"existing scale unknown",
                         root / "tpcds_db": b"existing scale unknown",
                         root / "tpch_50.duckdb": b"preserve SF50",
                         root / "tpcds_100.duckdb.wal": b"preserve WAL"}
            for path, content in old_files.items():
                path.write_bytes(content)
            actual = self.shell_paths(root, {"TPCH_SF": "100", "TPCDS_SF": "100"})
            self.assertEqual(actual["tpch"], root / "tpch_100.duckdb")
            self.assertEqual(actual["tpcds"], root / "tpcds_100.duckdb")
            self.assertEqual(set(root.iterdir()), set(old_files))
            for path, content in old_files.items():
                self.assertEqual(path.read_bytes(), content)

    def test_unknown_family_is_rejected(self):
        with self.assertRaises(ValueError):
            database_path("other", Path("/tmp"), {})


if __name__ == "__main__":
    unittest.main()
