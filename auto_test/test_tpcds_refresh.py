"""TPC-DS refresh provenance, exact exclusions, and three-tier coverage."""
from collections import Counter
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import balanced_benchmark as b
from benchmark_corpus import count_base_relations, historical_manifests, resolve_sql_path
import tpcds_refresh as refresh
from test_gen_outerjoin_benchmark import forbid_result_access
from benchmark_test_fixtures import historical_corpus


class TPCDSRefreshTest(unittest.TestCase):
    def test_all_three_tiers_retain_historical_join_expressions(self):
        with forbid_result_access():
            candidates = list(refresh.recovery_queries())
        self.assertEqual(len(candidates), 54)
        self.assertEqual(Counter((r["recovery_template"], r["semantic_tier"]) for r, _ in candidates),
                         {(t["name"], tier): 1 for t in refresh.policy()["templates"] for tier in b.TIERS})
        self.assertEqual(len({r["sql_fingerprint"] for r, _ in candidates}), 54)
        for row, sql in candidates:
            self.assertEqual(b.expression_key(sql, "tpcds"), row["expression_fingerprint"])
            self.assertEqual(count_base_relations(sql), row["relation_count"])
            self.assertGreaterEqual(len(set(row["join_vector"])), 2)
            self.assertIn(row["selectivity_predicate"], sql)
            self.assertLessEqual(float(row["target_max_fraction"]), .6)
            self.assertEqual(row["qualification_status"], "PENDING_CPU9_MEASUREMENT")
            self.assertNotIn("tm_off", row)
            self.assertNotIn("tm_on", row)
            self.assertEqual(b.digest(b.legacy.REPO_ROOT / row["source_location"]), row["source_sha256"])
            if row["selectivity_profile"].startswith("recovery_modulo_"):
                self.assertIn(f"({row['selectivity_anchor']} % 100) < ", sql)
                self.assertIn("NOT a business-semantic", row["filter_semantics"])

    def test_no_renaming_of_known_failed_historical_sql(self):
        known_bad = {r["sql_fingerprint"] for r in refresh.policy()["recovery_rejected_exact_sql"]}
        self.assertTrue(known_bad.isdisjoint(r["sql_fingerprint"] for r, _ in refresh.recovery_queries()))
        profiles = refresh.policy()["recovery_profiles"]
        self.assertEqual(len(profiles), 4)
        self.assertTrue(set(profiles).issubset(b.load_design()["profiles"]))
        for profile in profiles.values():
            self.assertTrue(all(b.legacy.fraction_in_band(f, tier) for f, tier in
                                zip(profile["calibration"]["observed_fractions"], b.load_design()["tiers"])))

    def test_exclusions_are_exact_not_whole_expressions(self):
        spec = refresh.policy()
        self.assertEqual(Counter(r["reason"] for r in spec["excluded"]),
                         {"timeout": 28, "measured_speedup_below_0.5": 8})
        active = b.read_manifest(historical_corpus(self) / "manifest.csv")
        self.assertTrue({r["sql_fingerprint"] for r in spec["excluded"]}.isdisjoint(
            r["sql_fingerprint"] for r in active))
        self.assertTrue(any("left_deep__ifilr__b21fdfc2__sel_low" in r["query_id"] for r in active))
        self.assertFalse(any("left_deep__ifilr__b21fdfc2__sel_high" in r["query_id"] for r in active))
        recovery = [r for r in active if r.get("recovery_template") == "storm10809_rdul"]
        # Later exact-query retirements remove the high-tier sibling; generation
        # still covers all tiers before those separately pinned policies apply.
        self.assertEqual({r["semantic_tier"] for r in recovery}, {"low", "medium"})
        generated = [r for r, _ in refresh.recovery_queries()
                     if r.get("recovery_template") == "storm10809_rdul"]
        self.assertEqual({r["semantic_tier"] for r in generated}, set(b.TIERS))

    def test_removed_sql_is_recoverable(self):
        archive = b.ROOT / "revisions/retired_tpcds_20261005/benchmark"
        rows = b.read_manifest(archive / "manifest.csv")
        self.assertEqual(len(rows), 36)
        for row in rows:
            self.assertEqual(b.digest(archive / row["path"]), row["content_sha256"])
            self.assertEqual(resolve_sql_path(row["query_class"], row["path"]), archive / row["path"])
        self.assertIn((None, archive / "manifest.csv"), list(historical_manifests()))

    def test_generation_is_idempotent_and_marker_cannot_be_ignored(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), forbid_result_access():
            root = Path(tmp)
            b.generate(root)
            first = (root / "benchmark/manifest.csv").read_bytes()
            b.generate(root)
            self.assertEqual(first, (root / "benchmark/manifest.csv").read_bytes())
            with self.assertRaisesRegex(ValueError, "new --root"):
                b.generate(root, per_family=9)
            self.assertEqual(first, (root / "benchmark/manifest.csv").read_bytes())


if __name__ == "__main__":
    unittest.main()
