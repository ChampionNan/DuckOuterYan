#!/usr/bin/env python3
"""Portable query generation must not depend on machine-local result files."""

import builtins
import contextlib
import csv
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
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
                            len(csv_rows(root / "active_timeout_exclusions.csv")),
                            0,
                        )
                        self.assertEqual(
                            {str(path.relative_to(legacy_root)) for path in legacy_root.glob("*/*.sql")},
                            MEMBERSHIP.COMPLETED_QUERY_PATHS,
                        )
                        manifests = ["manifest.csv", "timeout_exclusions.csv", "legacy_classification.csv"]
                        if not core_only:
                            manifests += [
                                "benchmark/manifest.csv", "industry_inspired/manifest.csv",
                                "supplemental/manifest.csv", "active_timeout_exclusions.csv",
                            ]
                        for manifest in manifests:
                            self.assertEqual(
                                csv_rows(root / manifest),
                                csv_rows(SCRIPT_DIR / "outerjoin_benchmark" / manifest),
                                manifest,
                            )

    def test_historical_timeout_exclusions_do_not_filter_mixed_v1(self):
        root = SCRIPT_DIR / "outerjoin_benchmark"
        active = csv_rows(root / "benchmark" / "manifest.csv")
        excluded = csv_rows(root / "active_timeout_exclusions.csv")
        pins = BENCHMARK.active_timeouts.EXCLUDED_QUERY_HASHES
        self.assertEqual(len(pins), 30)
        self.assertEqual(len(BENCHMARK.active_timeouts.T32_TIMEOUT_QUERY_HASHES), 9)
        self.assertEqual(excluded, [])
        active_paths = {row["path"] for row in active}
        expected = {
            f"{row['family']}/derived__{row['query_id']}.sql"
            for row in csv_rows(root / "manifest.csv")
        }
        for row in csv_rows(root / "industry_inspired" / "manifest.csv"):
            prefix = "derived" if row["evaluation_role"] == "legacy_performance_win" else "industry"
            expected.add(f"{row['family']}/{prefix}__{row['query_id']}.sql")
        self.assertEqual(len(expected), 206)
        self.assertEqual(active_paths, expected)
        self.assertTrue(set(pins) <= active_paths)
        self.assertEqual(
            {row["corpus_revision"] for row in active},
            {BENCHMARK.V1_CORPUS_REVISION},
        )
        self.assertTrue(all(len(set(row["join_vector"])) >= 2 for row in active))
        active_join_counts = Counter()
        for row in active:
            active_join_counts.update(row["join_vector"])
        self.assertLessEqual(
            max(active_join_counts.values()) - min(active_join_counts.values()), 1
        )
        active_by_path = {row["path"]: row for row in active}
        self.assertTrue(
            all(active_by_path[path]["content_sha256"] != digest for path, digest in pins.items())
        )
        for row in active:
            source_bytes = (root / row["source_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), row["content_sha256"])
            target = root / "benchmark" / row["path"]
            self.assertEqual(target.read_bytes(), source_bytes)
        BENCHMARK.validate_generated(root)

    def test_local_active_edit_fails_before_replacing_mixed_view(self):
        with tempfile.TemporaryDirectory(prefix="outeryan-active-pin-") as directory:
            root = Path(directory)
            BENCHMARK.generate_core(root)
            BENCHMARK.generate_active_benchmark(root, include_industry=False)
            active = root / "benchmark" / "manifest.csv"
            before = active.read_bytes()
            row = csv_rows(active)[0]
            target = root / "benchmark" / row["path"]
            target.write_text(target.read_text(encoding="utf-8") + "\n-- changed\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "locally modified active SQL"), forbid_result_access():
                BENCHMARK.generate_active_benchmark(root, include_industry=False)
            self.assertEqual(active.read_bytes(), before)

    def test_mixed_v1_requires_complete_core_coverage(self):
        root = SCRIPT_DIR / "outerjoin_benchmark"
        core = csv_rows(root / "manifest.csv")
        active = csv_rows(root / "benchmark" / "manifest.csv")
        BENCHMARK.validate_active_coverage(core, active, True)
        removed = next(row for row in active if row["evaluation_role"] == "benchmark_derived")
        with self.assertRaisesRegex(RuntimeError, "unexpected active core count"):
            BENCHMARK.validate_active_coverage(
                core, [row for row in active if row is not removed], True
            )

    def test_old_timeout_paths_reappear_only_with_new_content(self):
        root = SCRIPT_DIR / "outerjoin_benchmark"
        active = csv_rows(root / "benchmark" / "manifest.csv")
        active_by_path = {row["path"]: row for row in active}
        for path, old_hash in BENCHMARK.active_timeouts.T32_TIMEOUT_QUERY_HASHES.items():
            with self.subTest(path=path):
                self.assertIn(path, active_by_path)
                self.assertNotEqual(active_by_path[path]["content_sha256"], old_hash)

    def test_regeneration_preserves_unmanaged_files_and_rejects_local_sql_edits(self):
        with tempfile.TemporaryDirectory(prefix="outeryan-active-view-") as directory:
            root = Path(directory)
            BENCHMARK.generate_core(root)
            BENCHMARK.generate_active_benchmark(root, include_industry=False)
            extra = root / "benchmark" / "manifest copy.csv"
            extra.write_text("keep this local copy\n", encoding="utf-8")
            BENCHMARK.generate_active_benchmark(root, include_industry=False)
            self.assertEqual(extra.read_text(encoding="utf-8"), "keep this local copy\n")
            active = csv_rows(root / "benchmark" / "manifest.csv")
            target = root / "benchmark" / active[0]["path"]
            modified = target.read_text(encoding="utf-8") + "\n-- local change\n"
            target.write_text(modified, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "locally modified active SQL"):
                BENCHMARK.generate_active_benchmark(root, include_industry=False)
            self.assertEqual(target.read_text(encoding="utf-8"), modified)

    def test_v2_is_a_complete_bounded_selectivity_sweep_with_paired_controls(self):
        with tempfile.TemporaryDirectory(prefix="outeryan-v2-") as directory, forbid_result_access():
            root = Path(directory)
            self.assertEqual(BENCHMARK.generate_v2_core(root), 510)
            self.assertEqual(BENCHMARK.generate_v2_benchmark(root), 546)
            self.assertEqual(BENCHMARK.generate_v2_selectivity_stress(root), 84)
            self.assertEqual(BENCHMARK.generate_v2_job_regressions(root), 2)
            BENCHMARK.validate_v2_generated(root)
            core = csv_rows(root / "manifest.csv")
            active = csv_rows(root / "benchmark" / "manifest.csv")
            stress = csv_rows(root / "selectivity_stress" / "manifest.csv")
            regressions = csv_rows(root / "job_regressions" / "manifest.csv")
            self.assertEqual(
                {row["selectivity_tier"] for row in core},
                {"sel001", "sel01", "sel05"},
            )
            self.assertEqual(
                {row["selectivity_modulus"] for row in core},
                {"1000", "100", "20"},
            )
            self.assertEqual(
                {row["pattern_role"] for row in core},
                {
                    "v1_advantage_hypothesis",
                    "paired_structural_control",
                    "job_regression_guard",
                },
            )
            base_counts = {}
            base_vectors = {}
            for row in core:
                base_counts[row["base_query_id"]] = base_counts.get(row["base_query_id"], 0) + 1
                base_vectors.setdefault(row["base_query_id"], set()).add(row["join_vector"])
                sql = (root / "core" / row["path"]).read_text(encoding="utf-8")
                self.assertIn("-- corpus_version: v2", sql)
                self.assertIn(f"hash({row['selectivity_anchor']})", sql)
                self.assertGreaterEqual(len(set(row["join_vector"])), 2)
                if int(row["relation_count"]) >= 5:
                    self.assertEqual(set(row["join_vector"]), {"I", "L", "R", "F"})
            self.assertEqual(set(base_counts.values()), {3})
            self.assertEqual({len(vectors) for vectors in base_vectors.values()}, {1})
            self.assertEqual(
                {row["source_benchmark"] for row in core},
                {"TPC-H", "TPC-DS", "JOB", "SQLStorm"},
            )
            unique_core = {
                row["base_query_id"]: row for row in core
            }
            core_join_counts = Counter()
            for row in unique_core.values():
                core_join_counts.update(row["join_vector"])
            self.assertLessEqual(
                max(core_join_counts.values()) - min(core_join_counts.values()), 1
            )
            self.assertEqual(
                sum(row["evaluation_role"] != "benchmark_derived_v2" for row in active),
                36,
            )
            self.assertTrue(all(len(set(row["join_vector"])) >= 2 for row in active))
            active_join_counts = Counter()
            for row in active:
                active_join_counts.update(row["join_vector"])
            self.assertLessEqual(
                max(active_join_counts.values()) - min(active_join_counts.values()), 1
            )
            self.assertEqual(
                {
                    row["provenance_class"]
                    for row in active
                    if row["evaluation_role"] != "benchmark_derived_v2"
                },
                {
                    "graph_synthetic_control",
                    "industry_synthetic_control",
                    "schema_synthetic_control",
                },
            )
            self.assertEqual({row["headline_eligible"] for row in stress}, {"false"})
            self.assertEqual({row["performance_selected"] for row in stress}, {"false"})
            self.assertEqual({row["query_class"] for row in stress}, {"selectivity_stress"})
            self.assertTrue(all("observed_base_tm_speedup" not in row for row in stress))
            self.assertEqual(
                {row["selectivity_hash_buckets"] for row in stress},
                {"4000"},
            )
            self.assertEqual(
                {row["selectivity_bucket_threshold"] for row in stress},
                {"1", "2", "8", "400", "800", "2000", "3200"},
            )
            self.assertEqual(
                {row["target_fraction"] for row in stress},
                {
                    "0.000250", "0.000500", "0.002000", "0.100000",
                    "0.200000", "0.500000", "0.800000",
                },
            )
            self.assertEqual(
                {row["tier_balance"] for row in stress}, {"12 queries per tier"}
            )
            self.assertEqual(
                {row["distribution_claim"] for row in stress},
                {
                    "balanced tier counts; numeric levels and realized selectivity "
                    "are not claimed to be uniform"
                },
            )
            base_rows = {row["base_query_id"]: row for row in stress}
            self.assertEqual(len(base_rows), 12)
            self.assertEqual(
                {
                    row["base_query_id"]
                    for row in BENCHMARK.select_v2_stress_bases(root)
                },
                set(base_rows),
            )
            self.assertTrue(
                all(len(set(row["join_vector"])) >= 2 for row in stress)
            )
            self.assertTrue(all(int(row["relation_count"]) >= 4 for row in stress))
            self.assertEqual(
                {family: sum(row["family"] == family for row in base_rows.values())
                 for family in ("tpch", "tpcds", "job")},
                {"tpch": 4, "tpcds": 4, "job": 4},
            )
            for family in ("tpch", "tpcds", "job"):
                shapes = {
                    row["tree_shape"] for row in base_rows.values()
                    if row["family"] == family
                }
                self.assertTrue({"left_deep", "right_deep", "bushy"} <= shapes)
            self.assertEqual(
                {row["base_query_id"] for row in regressions},
                {"ojb_sqlstorm_job_11914_bdmx", "oy_jb_jb_bushy4a_v2"},
            )
            self.assertEqual(
                {row["disposition"] for row in regressions},
                {"retain_mixed_counterpart_in_main_benchmark"},
            )
            self.assertEqual(
                {row["measurement_status"] for row in regressions},
                {"requires_v2_remeasurement"},
            )
            self.assertTrue(
                all(len(set(row["join_vector"])) >= 2 for row in regressions)
            )


if __name__ == "__main__":
    unittest.main()
