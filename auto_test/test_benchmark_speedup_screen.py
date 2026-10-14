"""All-family exact-query screening, including threshold and archive checks."""
from collections import Counter
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import balanced_benchmark as b
import benchmark_speedup_screen as screen
import benchmark_retirements as retirements
import tpcds_selectivity_extension as extension
import benchmark_plan_cohort as cohort
import graph_dataset_extension
import graph_dataset_promotion
from benchmark_corpus import resolve_sql_path, historical_manifests
from test_gen_outerjoin_benchmark import forbid_result_access


class BenchmarkSpeedupScreenTest(unittest.TestCase):
    def test_strict_boundary_and_invalid_observations(self):
        result = dict(correct="TRUE", timing_status="measured", tm_off="1", tm_on="2")
        self.assertFalse(screen.below_threshold(result))
        self.assertTrue(screen.below_threshold(dict(result, tm_off="0.999999999")))
        self.assertFalse(screen.below_threshold(dict(result, tm_off="1.000000001")))
        slower = dict(result, tm_off="0.1")
        for changes in (dict(tm_off="nan"), dict(tm_on="inf"), dict(tm_on="0"),
                        dict(tm_off="-1"), dict(tm_on="NA"), dict(correct="TIMEOUT"),
                        dict(correct="FALSE"), dict(timing_status="fallback-skip")):
            with self.subTest(changes=changes):
                self.assertFalse(screen.below_threshold(dict(slower, **changes)))

    def test_exact_exclusions_and_pending_candidates(self):
        corpus = cohort.input_corpus()
        rows = b.validate(corpus)
        rows, _ = graph_dataset_extension.validate(corpus, rows)
        rows, _ = graph_dataset_promotion.validate(corpus, rows)
        self.assertEqual(Counter(r["family"] for r in rows), retirements.policy()["expected_counts_after"])
        rows, _ = retirements.validate(corpus, rows)
        spec = screen.policy()
        self.assertEqual(Counter(r["family"] for r in spec["excluded"]), dict(graph=3, tpch=1, tpcds=7, job=12))
        self.assertEqual(len(spec["previously_retired_tpcds_queries"]), 8)
        self.assertEqual(Counter(r["family"] for r in rows), extension.policy()["expected_counts_after"])
        self.assertEqual(Counter(r["family"] for r in rows if not extension.is_extension(r)),
                         dict(graph=177, tpch=179, tpcds=194, job=168))
        excluded = {r["sql_fingerprint"] for r in spec["excluded"]}
        self.assertTrue(excluded.isdisjoint(r["sql_fingerprint"] for r in rows))
        self.assertEqual(sum(r.get("evaluation_role") == "historical_selectivity_recovery" for r in rows), 47)
        self.assertTrue(all(float(r["qualification_min_speedup"]) == .5 for r in rows))
        self.assertTrue(all(float(r["qualification_min_runtime_s"]) == (0 if r["family"] == "tpcds" else 1)
                            for r in rows))
        self.assertTrue(any("job_10a_cast_credits__right_deep__lrif__92d3ab51__sel_low" in r["query_id"] for r in rows))
        recovery_paths = (corpus / "tpcds_recovery.txt").read_text().splitlines()
        self.assertEqual(len(recovery_paths), 47)
        self.assertEqual(set(recovery_paths), {r["path"] for r in rows
                                              if r.get("evaluation_role") == "historical_selectivity_recovery"})
        self.assertTrue(all((corpus / path).is_file() for path in recovery_paths))
        self.assertTrue(set(recovery_paths).isdisjoint(r["path"] for r in spec["excluded"]))

    def test_archive_preserves_sql_and_original_manifest(self):
        archived_ids = set()
        for revision, expected in (("retired_speedup_20261005", 5), ("retired_speedup_20261007", 7),
                                   ("retired_speedup_20261008", 11)):
            with self.subTest(revision=revision):
                archive = b.ROOT / "revisions" / revision / "benchmark"
                rows = b.read_manifest(archive / "manifest.csv")
                self.assertEqual(len(rows), expected)
                ids = {r["query_id"] for r in rows}
                self.assertTrue(archived_ids.isdisjoint(ids))
                archived_ids.update(ids)
                for row in rows:
                    self.assertEqual(b.digest(archive / row["path"]), row["content_sha256"])
                    self.assertEqual(resolve_sql_path(row["query_class"], row["path"]), archive / row["path"])
                    self.assertFalse((b.ROOT / "benchmark" / row["path"]).exists())
                self.assertIn((None, archive / "manifest.csv"), list(historical_manifests()))
        self.assertEqual(archived_ids, {r["query_id"] for r in screen.policy()["excluded"]})

    def test_scoped_inclusive_boundary_and_disabled_correctness(self):
        result = dict(correct="NOT-CHECKED", correctness_check="disabled",
                      timing_status="measured", tm_off="0.7", tm_on="1")
        self.assertFalse(screen.below_threshold(result, .7, inclusive=True))
        self.assertFalse(screen.below_threshold(result, .7, allow_unchecked=True))
        self.assertTrue(screen.below_threshold(result, .7, inclusive=True, allow_unchecked=True))
        for change in (dict(tm_off="0.700000001"), dict(correctness_check="enabled"),
                       dict(correct="FALSE"), dict(correct="TIMEOUT"), dict(tm_on="nan"),
                       dict(timing_status="fallback-skip")):
            self.assertFalse(screen.below_threshold(dict(result, **change), .7,
                                                    inclusive=True, allow_unchecked=True))
        spec = screen.policy()
        old = json.loads((b.ROOT / "sources/speedup_screen_20261007.json").read_text())
        self.assertEqual(spec["excluded"][:len(old["excluded"])], old["excluded"])
        new = [r for r in spec["excluded"] if r.get("screen_rule")]
        self.assertEqual(Counter(r["family"] for r in new), dict(graph=2, job=9))
        self.assertTrue(all("correct" not in r and "duckdb_s" not in r for r in new))
        self.assertEqual(spec["minimum_speedup"], .5)  # No dynamic global 0.7 filter.

    def test_tpcds_retirement_is_exact_query_not_whole_pattern(self):
        excluded = {r["query_id"] for r in screen.policy()["excluded"] if r["family"] == "tpcds"}
        aggregate_patterns = ("q40_alt_count__rfil__6fd66f8d", "q40_rdax_count__filr__a8fcb1be",
                              "q40_right_count__lrfi__4fb69227")
        expected = {f"aggregate__tpcds__recovery__{pattern}__sel_{tier}"
                    for pattern in aggregate_patterns for tier in ("medium", "high")}
        join_pattern = "join__tpcds__recovery__storm10809_rdul__rfil__5fa2ea2c"
        expected.add(join_pattern + "__sel_high")
        self.assertEqual(excluded, expected)
        active = {r["query_id"] for r in b.validate(b.ROOT / "benchmark")}
        retained_variants = {f"aggregate__tpcds__recovery__{pattern}__sel_low" for pattern in aggregate_patterns}
        retained_variants.update(join_pattern + "__sel_" + tier for tier in ("low", "medium"))
        self.assertTrue(retained_variants.issubset(active))

    def test_screen_metadata_and_regeneration_without_results(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), forbid_result_access():
            root = Path(tmp)
            b.generate(root)
            manifest = root / "benchmark/manifest.csv"
            original = manifest.read_bytes()
            self.assertEqual(original, (b.ROOT / "benchmark/manifest.csv").read_bytes())
            b.generate(root)
            self.assertEqual(original, manifest.read_bytes())
            marker_path = root / "benchmark" / screen.MARKER
            original_marker = marker_path.read_text()
            marker = json.loads(original_marker)
            marker["counts"]["graph"] += 1
            marker_path.write_text(json.dumps(marker))
            with self.assertRaisesRegex(ValueError, "Historical cohort dependency|screen counts"):
                b.validate(root / "benchmark")
            marker_path.write_text(original_marker)
            marker = json.loads(original_marker)
            marker["rule_removed_counts"]["graph-job-le-0.7-20261008"]["graph"] += 1
            marker_path.write_text(json.dumps(marker))
            with self.assertRaisesRegex(ValueError, "Historical cohort dependency|Scoped speed-up exclusion counts"):
                b.validate(root / "benchmark")
            marker_path.write_text(original_marker)
            excluded_path = root / "benchmark/speedup_excluded.csv"
            excluded = b.read_manifest(excluded_path)
            excluded[0]["duckdb_s"] = "1000"
            b.write_csv(excluded_path, excluded)
            with self.assertRaisesRegex(ValueError, "Historical cohort dependency|Excluded-query evidence changed"):
                b.validate(root / "benchmark")


if __name__ == "__main__":
    unittest.main()
