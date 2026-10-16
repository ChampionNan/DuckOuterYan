#!/usr/bin/env python3
"""Portable query generation must not depend on machine-local result files."""

import builtins
import contextlib
import csv
import hashlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
ARCHIVE = SCRIPT_DIR / "outerjoin_benchmark" / "revisions" / "semantic_ranges_20260929"
with mock.patch.object(sys, "path", [str(SCRIPT_DIR)] + sys.path):
    import gen_outerjoin_benchmark as BENCHMARK
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
