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
ARCHIVE = SCRIPT_DIR / "outerjoin_benchmark" / "revisions" / "semantic_ranges_20260929"
with mock.patch.object(sys, "path", [str(SCRIPT_DIR)] + sys.path):
    import gen_outerjoin_benchmark as BENCHMARK
    import gen_queries as LEGACY
    import legacy_corpus as MEMBERSHIP


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class Python37String(str):
    """Exercise generation without string APIs added after Python 3.7."""

    def __getattribute__(self, name):
        if name in ("removeprefix", "removesuffix"):
            raise AttributeError(name)
        return super().__getattribute__(name)


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
    def test_band_boundaries_have_no_overlap_and_exclude_above_eighty_percent(self):
        def memberships(value):
            return [spec["name"] for spec in BENCHMARK.SEMANTIC_DESIGN["tiers"]
                    if BENCHMARK.fraction_in_band(value, spec)]
        self.assertEqual(memberships(0), [])
        self.assertEqual(memberships(.049), ["low"])
        self.assertEqual(memberships(.05), ["medium"])
        self.assertEqual(memberships(.4), ["high"])
        self.assertEqual(memberships(.8), ["high"])
        self.assertEqual(memberships(.801), [])

    def test_source_filter_families_are_retained(self):
        seeds = {seed.seed_id: seed for seed in BENCHMARK.SEEDS}
        expected = {
            "tpch_q09_supply_chain": ("p.p_name", "LIKE"),
            "tpcds_q93_return_reason": ("r.r_reason_desc", "="),
            "job_17a_movie_annotations": ("n.name", "LIKE"),
            "job_16a_skeleton": ("t.episode_nr", ">="),
            "job_01a_skeleton": ("it.info", "="),
        }
        for seed_id, (column, operator) in expected.items():
            metadata = BENCHMARK.seed_filter_metadata(seeds[seed_id], "low")
            self.assertIn(f"{column} {operator}", metadata["selectivity_predicate"])
            self.assertNotIn("synthetic control", metadata["source_filter_adaptation"])

    def test_semantic_bands_are_nested_nonempty_business_cohorts(self):
        for seed in BENCHMARK.SEEDS:
            spec = BENCHMARK.SEMANTIC_DESIGN["seeds"][seed.seed_id]
            self.assertEqual(spec["source_sha256"], seed.source_hash)
            profile = BENCHMARK.SEMANTIC_DESIGN["profiles"][spec["profile"]]
            if "bounds" in profile:
                self.assertEqual(profile["bounds"], sorted(profile["bounds"]))
            counts = profile["calibration"]["qualified_rows"]
            self.assertEqual(counts, sorted(set(counts)))
            self.assertGreater(counts[0], 0)
            self.assertTrue(any(relation.split()[-1] == spec["column"].split(".")[0]
                                for relation in seed.relations))
            for tier in BENCHMARK.SEMANTIC_TIERS:
                metadata = BENCHMARK.seed_filter_metadata(seed, tier)
                self.assertEqual(metadata["calibration_in_range"], "true", (seed.seed_id, tier))
                self.assertNotIn(".id", metadata["selectivity_predicate"])

    def test_range_sweep_replaces_old_where_and_preserves_join_predicates(self):
        sql = "SELECT * FROM a LEFT JOIN b ON a.id=b.id WHERE a.id % 1000=0 GROUP BY ALL;"
        expected = "SELECT * FROM a LEFT JOIN b ON a.id=b.id WHERE b.price <= 50 GROUP BY ALL;"
        self.assertEqual(BENCHMARK.replace_where(sql, "b.price <= 50"), expected)
        # A surviving hash/mod conjunct is rejected even if a comment names the new predicate.
        row = {"path": "example.sql", "selectivity_predicate": "b.price <= 50",
               "filter_design_revision": BENCHMARK.V1_CORPUS_REVISION, "calibration_in_range": "true"}
        with self.assertRaisesRegex(RuntimeError, "key sampling"):
            BENCHMARK.validate_semantic_query(sql, row)
        with self.assertRaisesRegex(RuntimeError, "WHERE differs"):
            BENCHMARK.validate_semantic_query(expected.replace("<= 50", "<= 50 AND b.price > 49"), row)

    def test_job_foreign_keys_are_never_substituted_with_unrelated_ids(self):
        self.assertEqual(BENCHMARK.active_edge_predicate("chn.id = ci.person_role_id"),
                         "chn.id = ci.person_role_id")
        for seed in BENCHMARK.SEEDS:
            if seed.family == "job":
                self.assertTrue(any(relation.split()[0] == "title" for relation in seed.relations))

    def test_pinned_membership_matches_checked_in_manifests(self):
        root = ARCHIVE
        classification = csv_rows(SCRIPT_DIR / "outerjoin_benchmark" / "legacy_classification.csv")
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
            {row["path"] for row in csv_rows(SCRIPT_DIR / "outerjoin_benchmark" / "timeout_exclusions.csv")},
        )
        self.assertEqual(
            MEMBERSHIP.LEGACY_OUTERYAN_WINS,
            tuple(
                (row["family"], Path(row["path"]).name)
                for row in csv_rows(root / "supplemental" / "manifest.csv")
            ),
        )
        self.assertEqual(len(MEMBERSHIP.LEGACY_OUTERYAN_WINS), 28)
        for row in classification:
            if row["path"] in MEMBERSHIP.TIMEOUT_QUERY_PATHS:
                self.assertEqual(row["content_status"], "removed_timeout_sql")
                self.assertEqual(row["content_sha256"], "")
        for family, filename in MEMBERSHIP.LEGACY_OUTERYAN_WINS:
            self.assertIn(f"{family}/{filename}", MEMBERSHIP.COMPLETED_QUERY_PATHS)

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

    def test_unique_generation_is_complete_deterministic_and_ignores_results(self):
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
            tiers = tuple((Python37String(tier), target, description)
                          for tier, target, description in BENCHMARK.V2_SELECTIVITY_TIERS)
            with mock.patch.multiple(LEGACY, **legacy_paths), mock.patch.object(
                BENCHMARK, "LEGACY_ROOT", legacy_root
            ), mock.patch.object(BENCHMARK, "V2_SELECTIVITY_TIERS", tiers), mock.patch.dict(
                sys.modules, {"gen_queries": LEGACY}
            ), forbid_result_access():
                root = scratch / "unique"
                with contextlib.redirect_stdout(io.StringIO()):
                    BENCHMARK.generate_unified(root)
                active = csv_rows(root / "benchmark" / "manifest.csv")
                self.assertEqual(len(active), 650)
                self.assertEqual(len({row["sql_fingerprint"] for row in active}), 650)
                self.assertEqual(Counter(row["query_class"] for row in active),
                                 {"join": 480, "graph": 68, "aggregate": 102})
                self.assertFalse((root / "v2").exists())
                self.assertFalse((root / "v3").exists())
                self.assertEqual(sum(row["selectivity_stress"] == "true" for row in active), 18)
                self.assertEqual(sum(row["regression_guard"] == "true" for row in active), 2)
                aliases = csv_rows(root / "benchmark" / "aliases.csv")
                self.assertEqual(len(aliases), 910)
                self.assertEqual({row["canonical_query_id"] for row in aliases},
                                 {row["query_id"] for row in active})
                self.assertEqual(active, csv_rows(SCRIPT_DIR / "outerjoin_benchmark" / "revisions" /
                                                 "unique_semantic_20260929" / "benchmark" / "manifest.csv"))
                before = (root / "benchmark" / "manifest.csv").read_bytes()
                with contextlib.redirect_stdout(io.StringIO()):
                    BENCHMARK.generate_unified(root)
                self.assertEqual(before, (root / "benchmark" / "manifest.csv").read_bytes())

    def test_mixed_v1_preserves_all_source_queries(self):
        root = ARCHIVE
        active = csv_rows(root / "benchmark" / "manifest.csv")
        active_paths = {row["path"] for row in active}
        expected = {
            f"{row['family']}/derived__sem__{row['query_id']}.sql"
            for row in csv_rows(root / "manifest.csv")
        }
        for row in csv_rows(root / "industry_inspired" / "manifest.csv"):
            prefix = (
                "industry"
                if row["evaluation_role"].startswith("industry_pattern")
                else "derived"
            )
            expected.add(f"{row['family']}/{BENCHMARK.active_query_id(prefix, row)}.sql")
        self.assertEqual(len(expected), 224)
        self.assertEqual(active_paths, expected)
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
        graph_rows = [row for row in active if row["family"] == "graph"]
        self.assertEqual(len(graph_rows), 25)
        self.assertEqual(
            Counter(row["tree_shape"] for row in graph_rows),
            Counter({"bushy": 10, "left_deep": 7, "right_deep": 8}),
        )
        self.assertEqual(
            {row["evaluation_role"] for row in graph_rows}, {"graph_pattern"}
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
        root = ARCHIVE
        core = csv_rows(root / "manifest.csv")
        active = csv_rows(root / "benchmark" / "manifest.csv")
        BENCHMARK.validate_active_coverage(core, active, True)
        removed = next(row for row in active if row["evaluation_role"] == "benchmark_derived")
        with self.assertRaisesRegex(RuntimeError, "unexpected active core count"):
            BENCHMARK.validate_active_coverage(
                core, [row for row in active if row is not removed], True
            )

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
            self.assertEqual(BENCHMARK.generate_v2_benchmark(root, ARCHIVE), 564)
            self.assertEqual(BENCHMARK.generate_v2_job_regressions(root, ARCHIVE), 2)
            BENCHMARK.validate_v2_generated(root)
            core = csv_rows(root / "manifest.csv")
            active = csv_rows(root / "benchmark" / "manifest.csv")
            regressions = csv_rows(root / "job_regressions" / "manifest.csv")
            self.assertEqual(
                {row["selectivity_tier"] for row in core},
                {"sel_low", "sel_medium", "sel_high"},
            )
            self.assertEqual(
                {row["calibration_in_range"] for row in core},
                {"true"},
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
                BENCHMARK.validate_semantic_query(sql, row)
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
                54,
            )
            graph_rows = [row for row in active if row["family"] == "graph"]
            self.assertEqual(len(graph_rows), 25)
            self.assertEqual(
                Counter(row["tree_shape"] for row in graph_rows),
                Counter({"bushy": 10, "left_deep": 7, "right_deep": 8}),
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

    def test_v3_balances_source_derived_root_aggregation_coverage(self):
        with tempfile.TemporaryDirectory(prefix="outeryan-v3-") as directory, forbid_result_access():
            root = Path(directory)
            self.assertEqual(BENCHMARK.generate_v3_core(root), 102)
            self.assertEqual(BENCHMARK.generate_v3_benchmark(root), 102)
            self.assertEqual(BENCHMARK.generate_v3_selectivity_stress(root, ARCHIVE / "v2", ARCHIVE), 18)
            BENCHMARK.validate_v3_generated(root)
            core = csv_rows(root / "manifest.csv")
            active = csv_rows(root / "benchmark" / "manifest.csv")
            stress = csv_rows(root / "selectivity_stress" / "manifest.csv")
            self.assertEqual(
                Counter(row["aggregate_variant"] for row in core),
                Counter(
                    {
                        "global_count": 42,
                        "grouped_sum": 30,
                        "grouped_min": 15,
                        "grouped_max": 15,
                    }
                ),
            )
            self.assertEqual(
                Counter(row["source_benchmark"] for row in core),
                Counter({"TPC-H": 15, "TPC-DS": 21, "JOB": 30, "SQLStorm": 36}),
            )
            self.assertEqual(
                Counter(row["family"] for row in active),
                Counter({"tpch": 27, "tpcds": 33, "job": 42}),
            )
            for tree_shape in {row["tree_shape"] for row in active}:
                aggregate_counts = Counter(
                    row["aggregate_variant"]
                    for row in active
                    if row["tree_shape"] == tree_shape
                )
                shape_count = sum(aggregate_counts.values())
                for variant, target in BENCHMARK.V3_AGGREGATE_TARGET_COUNTS.items():
                    expected = shape_count * target / BENCHMARK.V3_BENCHMARK_QUERY_COUNT
                    self.assertLessEqual(abs(aggregate_counts[variant] - expected), 1.0)
            join_counts = Counter()
            for row in active:
                sql = (root / "benchmark" / row["path"]).read_text(encoding="utf-8")
                self.assertIn("-- corpus_version: v3", sql)
                self.assertTrue(
                    any(
                        token in sql.upper()
                        for token in ("COUNT(", "MIN(", "MAX(", "SUM(")
                    )
                )
                self.assertGreaterEqual(len(set(row["join_vector"])), 2)
                join_counts.update(row["join_vector"])
            self.assertLessEqual(max(join_counts.values()) - min(join_counts.values()), 1)
            self.assertEqual({row["corpus_version"] for row in stress}, {"v3"})
            self.assertEqual({row["headline_eligible"] for row in stress}, {"false"})
            self.assertEqual({row["performance_selected"] for row in stress}, {"false"})
            self.assertEqual({row["query_class"] for row in stress}, {"selectivity_stress"})
            self.assertTrue(all("observed_base_tm_speedup" not in row for row in stress))
            self.assertEqual(
                {row["semantic_tier"] for row in stress},
                {"low", "medium", "high"},
            )
            for row in stress:
                sql = (root / "selectivity_stress" / row["path"]).read_text()
                BENCHMARK.validate_semantic_query(sql, row)
            self.assertEqual({row["tier_balance"] for row in stress}, {"6 queries per tier"})
            base_rows = {row["base_query_id"]: row for row in stress}
            self.assertEqual(len(base_rows), 6)
            self.assertEqual(
                {
                    row["base_query_id"]
                    for row in BENCHMARK.select_v3_stress_bases(ARCHIVE / "v2", ARCHIVE)
                },
                set(base_rows),
            )
            self.assertEqual(
                Counter(row["family"] for row in base_rows.values()),
                Counter({"tpch": 2, "tpcds": 2, "job": 2}),
            )
            self.assertEqual(
                Counter(row["tree_shape"] for row in base_rows.values()),
                Counter({"left_deep": 2, "right_deep": 2, "bushy": 2}),
            )
            self.assertEqual(
                {row["source_benchmark"] for row in base_rows.values()},
                {"TPC-H", "TPC-DS", "JOB", "SQLStorm"},
            )


class UnifiedCorpusIdentityTest(unittest.TestCase):
    def test_identity_ignores_only_comments_and_formatting(self):
        fingerprint = BENCHMARK.sql_fingerprint
        sql = "SELECT a.id FROM a LEFT JOIN b ON a.id=b.id WHERE a.name='Ab C';"
        equivalent = "-- provenance\nselect a.id FROM a /* comment */ LEFT JOIN b ON a.id = b.id WHERE a.name = 'Ab C';"
        self.assertEqual(fingerprint(sql, 'tpch'), fingerprint(equivalent, 'TPC-H'))
        for changed in (sql.replace("'Ab C'", "'ab C'"), sql.replace('LEFT', 'RIGHT'),
                        sql.replace('a.id=b.id', 'a.id=b.other')):
            self.assertNotEqual(fingerprint(sql, 'tpch'), fingerprint(changed, 'tpch'))
        self.assertNotEqual(fingerprint(sql, 'tpch'), fingerprint(sql, 'tpcds'))

    def test_every_historical_alias_preserves_sql_and_has_one_canonical_target(self):
        from benchmark_corpus import resolve_sql_path
        root = SCRIPT_DIR / 'outerjoin_benchmark'
        rows = csv_rows(root / 'benchmark/manifest.csv')
        canonical = {row['query_id']: row for row in rows}
        for row in rows:
            if row['query_class'] == 'graph':
                old_path = row['path'].replace('/graph__', '/control__', 1)
                self.assertEqual(resolve_sql_path('control', old_path, root),
                                 root / 'benchmark' / row['path'])
        for alias in csv_rows(root / 'benchmark/aliases.csv'):
            old = resolve_sql_path(alias['workload_category'], alias['sql_path'], root)
            fingerprint = BENCHMARK.sql_fingerprint(old.read_text(), alias['family'])
            self.assertEqual(fingerprint, canonical[alias['canonical_query_id']]['sql_fingerprint'])
            self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(), alias['content_sha256'])


if __name__ == "__main__":
    unittest.main()
