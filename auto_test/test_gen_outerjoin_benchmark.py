#!/usr/bin/env python3
"""Portable query generation must not depend on machine-local result files."""

import builtins
import contextlib
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
with mock.patch.object(sys, "path", [str(SCRIPT_DIR)] + sys.path):
    import gen_outerjoin_benchmark as BENCHMARK
    import gen_queries as LEGACY
    import legacy_corpus as MEMBERSHIP


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@contextlib.contextmanager
def forbid_result_access():
    """Cover both builtin open() and pathlib/io.open() reads."""
    def guard(original):
        def checked(file, *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)):
                if "results" in Path(os.fsdecode(file)).parts:
                    raise AssertionError(f"Generator accessed local experiment results: {file}")
            return original(file, *args, **kwargs)
        return checked

    with mock.patch("builtins.open", side_effect=guard(builtins.open)), mock.patch(
        "io.open", side_effect=guard(io.open)
    ):
        yield


class PortableBenchmarkGenerationTest(unittest.TestCase):
    def test_pinned_membership_matches_checked_in_manifests(self):
        root = SCRIPT_DIR / "outerjoin_benchmark"
        classification = csv_rows(root / "legacy_classification.csv")
        self.assertEqual(
            [query.path for query in MEMBERSHIP.LEGACY_QUERIES],
            [row["path"] for row in classification],
        )
        self.assertEqual(len({query.path for query in MEMBERSHIP.LEGACY_QUERIES}), 254)
        self.assertEqual(len(MEMBERSHIP.COMPLETED_QUERY_PATHS), 170)
        self.assertEqual(len(MEMBERSHIP.TIMEOUT_QUERY_PATHS), 84)
        self.assertTrue(MEMBERSHIP.COMPLETED_QUERY_PATHS.isdisjoint(MEMBERSHIP.TIMEOUT_QUERY_PATHS))
        self.assertEqual(
            MEMBERSHIP.TIMEOUT_QUERY_PATHS,
            {row["path"] for row in csv_rows(root / "timeout_exclusions.csv")},
        )
        self.assertEqual(
            MEMBERSHIP.LEGACY_OUTERYAN_WINS,
            tuple(
                (row["family"], Path(row["path"]).name, row["observed_tm_speedup"])
                for row in csv_rows(root / "supplemental" / "manifest.csv")
            ),
        )
        self.assertEqual(len(MEMBERSHIP.LEGACY_OUTERYAN_WINS), 28)
        for family, filename, speedup in MEMBERSHIP.LEGACY_OUTERYAN_WINS:
            self.assertIn(f"{family}/{filename}", MEMBERSHIP.COMPLETED_QUERY_PATHS)
            self.assertGreater(float(speedup), 1.0)

    def test_legacy_import_does_not_need_results_or_generated_manifests(self):
        with tempfile.TemporaryDirectory(prefix="outeryan-import-") as directory:
            root = Path(directory)
            for filename in ("gen_queries.py", "legacy_corpus.py"):
                shutil.copyfile(SCRIPT_DIR / filename, root / filename)
            code = (
                "from pathlib import Path; import gen_queries; "
                "assert Path(gen_queries.__file__).parent == Path.cwd(); "
                "assert len(gen_queries.TIMEOUT_QUERY_PATHS) == 84; "
                "assert gen_queries.TIMEOUT_QUERY_PATHS <= gen_queries.EXCLUDED_CORPUS_QUERIES"
            )
            result = subprocess.run(
                [sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=30
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((root / "results").exists())

    def test_full_and_core_only_generation_without_result_access(self):
        with tempfile.TemporaryDirectory(prefix="outeryan-generation-") as directory:
            scratch = Path(directory)
            legacy_root = scratch / "legacy"
            legacy_paths = {
                "BASE": str(legacy_root),
                "GRAPH_BASE": str(legacy_root / "graph"),
                "PRED_DIR": str(legacy_root / "graph"),
                "TPCH_DIR": str(legacy_root / "tpch"),
                "TPCDS_DIR": str(legacy_root / "tpcds"),
                "JOB_DIR": str(legacy_root / "job"),
            }
            with mock.patch.multiple(LEGACY, **legacy_paths), mock.patch.object(
                BENCHMARK, "LEGACY_ROOT", legacy_root
            ), mock.patch.dict(sys.modules, {"gen_queries": LEGACY}), forbid_result_access():
                for core_only, count in ((False, 206), (True, 170)):
                    with self.subTest(core_only=core_only):
                        root = scratch / ("core-only" if core_only else "full")
                        argv = ["gen_outerjoin_benchmark.py", "--root", str(root)]
                        if core_only:
                            argv.append("--core-only")
                        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                            BENCHMARK.main()
                        active = csv_rows(root / "benchmark" / "manifest.csv")
                        self.assertEqual(len(active), count)
                        self.assertEqual(
                            {str(path.relative_to(legacy_root)) for path in legacy_root.glob("*/*.sql")},
                            MEMBERSHIP.COMPLETED_QUERY_PATHS,
                        )
                        manifests = ["manifest.csv", "timeout_exclusions.csv", "legacy_classification.csv"]
                        if not core_only:
                            manifests += [
                                "benchmark/manifest.csv", "industry_inspired/manifest.csv",
                                "supplemental/manifest.csv",
                            ]
                        for manifest in manifests:
                            self.assertEqual(
                                csv_rows(root / manifest),
                                csv_rows(SCRIPT_DIR / "outerjoin_benchmark" / manifest),
                                manifest,
                            )


if __name__ == "__main__":
    unittest.main()
