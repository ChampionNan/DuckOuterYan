"""Candidate construction and qualification tests; never run the expensive corpus."""
from collections import Counter
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import balanced_benchmark as b
from benchmark_corpus import count_base_relations
import tpcds_refresh as refresh
import benchmark_speedup_screen as screen
import benchmark_retirements as retirements
import graph_dataset_promotion as promotion
import graph_dataset_extension as graph_extension
import tpcds_selectivity_extension as extension
import benchmark_plan_cohort as cohort
from test_gen_outerjoin_benchmark import forbid_result_access


class BalancedBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = json.loads(b.DESIGN.read_text())
        cls.evidence = json.loads(b.EVIDENCE.read_text())
        cls.groups = b.candidate_rows(cls.design, cls.evidence)

    def test_pre_cohort_matrix_and_mixed_kinds(self):
        corpus = cohort.input_corpus()
        rows = b.validate(corpus)
        expected = dict(retirements.policy()["expected_counts_after"], graph=172)
        self.assertEqual(len(rows), sum(expected.values()))
        self.assertEqual(Counter(r["family"] for r in rows), expected)
        before_promotion, _ = graph_extension.validate(corpus, rows)
        before_retirement, _ = promotion.validate(corpus, before_promotion)
        before_retirement, _ = retirements.validate(corpus, before_retirement)
        before_screen = [r for r in before_retirement if not extension.is_extension(r)] + screen.policy()["excluded"]
        self.assertEqual(Counter((r["family"], r["semantic_tier"], r["tree_shape"]) for r in before_screen if r["family"] != "tpcds"),
                         {(f, t, s):20 for f in ("graph", "tpch", "job") for t in b.TIERS for s in b.SHAPES})
        self.assertTrue(all(len(set(r["join_vector"])) >= 2 for r in rows))
        self.assertFalse(any(r["source_seed"] == "tpcds_q72_fulfillment" for r in rows))
        self.assertEqual(self.design["curation"]["timeout_seconds"], 600)
        self.assertTrue(all(r["qualification_timeout_seconds"] == "600" for r in rows))
        graph = [r for r in rows if r["family"] == "graph"]
        self.assertEqual(Counter(int(r["relation_count"]) for r in graph), {4: 121, 5: 51})
        for tier in b.TIERS:
            for shape in b.SHAPES:
                self.assertEqual(Counter(int(r["relation_count"]) for r in graph
                                         if r["semantic_tier"] == tier and r["tree_shape"] == shape),
                                 {4: ({"bushy": 11, "left_deep": 12}.get(shape, 14) if tier == "low" else 14),
                                  5: ({"left_deep": 5, "right_deep": 4}.get(shape, 6)
                                      if tier == "low" else 6)})
        self.assertIn("industry_synthetic_control", {r["provenance_class"] for r in rows})
        banned = {e["expression_fingerprint"] for e in self.evidence["excluded"]}
        self.assertTrue(banned.isdisjoint(r["expression_fingerprint"] for r in rows
                                         if not refresh.is_recovery(r) and not extension.is_extension(r)))

    def test_historical_cases_preserve_sql_and_are_not_band_calibrated(self):
        active = b.ROOT / "benchmark"
        self.assertFalse(any(b.is_historical_case(r) for r in b.validate(active)))
        self.assertEqual((active / "historical_cases.txt").read_text(), "")
        corpus = b.ROOT / "revisions/retired_tpcds_20261005/benchmark"
        rows = [r for r in b.read_manifest(corpus / "manifest.csv") if b.is_historical_case(r)]
        self.assertEqual(len(rows), 3)
        for row in rows:
            original = b.legacy.REPO_ROOT / row["source_location"]
            self.assertEqual((corpus / row["path"]).read_bytes(), original.read_bytes())
            self.assertEqual(row["semantic_tier"], "historical_unbanded")
            self.assertEqual(row["target_min_fraction"], "")
            self.assertEqual(row["target_max_fraction"], "")
            self.assertEqual(row["calibration_in_range"], "not_applicable")
            self.assertEqual(row["qualification_status"], "PENDING_CPU9_MEASUREMENT")

    def test_graph_caps_filter_each_non_anchor_input_without_changing_join_structure(self):
        corpus = b.ROOT / "benchmark"
        for row in b.read_manifest(corpus / "manifest.csv"):
            if row["family"] != "graph":
                continue
            sql = (corpus / row["path"]).read_text()
            inputs = json.loads(row["input_filter_profiles_json"])
            self.assertEqual(len(inputs), int(row["relation_count"]) - 1)
            self.assertEqual(count_base_relations(sql), int(row["relation_count"]))
            self.assertIn("__inputcap1__", row["query_id"])
            self.assertEqual(b.expression_key(sql, "graph"), row["expression_fingerprint"])
            outer_where = sql.split("\nWHERE ")[-1].split("\nGROUP BY")[0].rstrip(";\n")
            self.assertEqual(outer_where, row["selectivity_predicate"])
            cap = (10, 20, 40)[b.TIERS.index(row["semantic_tier"])]
            if row.get("graph_dataset") == "epinions":
                cap = {"low": 539, "medium": 824}[row["semantic_tier"]]
            for extra in inputs:
                alias = extra["relation"]
                self.assertNotEqual(alias, "R1")
                self.assertIn(f"(SELECT src, dst FROM {alias} WHERE src <= {cap}) {alias}", sql)
                self.assertEqual(extra["predicate"], f"{alias}.src <= {cap}")
                self.assertLess(extra["calibration_fraction"], .3)

    def test_reserve_generation_does_not_repeat_historical_cases(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), forbid_result_access():
            root = Path(tmp)
            b.generate(root, per_family=9, batch=1)
            rows = b.validate(root / "benchmark")
            self.assertEqual(len(rows), 36)
            self.assertFalse(any(b.is_historical_case(r) for r in rows))
            self.assertEqual((root / "benchmark/historical_cases.txt").read_text(), "")

    def test_composite_edges_are_complete(self):
        predicate = "a.item = b.item AND a.ticket = b.ticket AND a.store = b.store"
        self.assertEqual(b.full_equality(predicate), predicate)

    def test_graph_branch_is_not_star_and_can_be_bushy(self):
        seeds = [s for s in b.graph_seeds() if s.topology == "branch"]
        self.assertTrue(seeds)
        for seed in seeds:
            self.assertIsNotNone(b.legacy.bushy_root_partition(seed))

    def test_bands_have_no_overlap_and_cap_at_sixty(self):
        bands = self.design["tiers"]
        for fraction, expected in ((0, []), (.04, ["low"]), (.05, ["medium"]),
                                   (.4, ["high"]), (.6, ["high"]), (.61, [])):
            self.assertEqual([s["name"] for s in bands if b.legacy.fraction_in_band(fraction, s)], expected)

    def test_disjoint_reserve_batch(self):
        first = {g[0]["expression_fingerprint"] for g in b.select_groups(self.groups, batch=0)}
        second = {g[0]["expression_fingerprint"] for g in b.select_groups(self.groups, batch=1)}
        self.assertEqual(len(first), 240)
        self.assertEqual(len(second), 240)
        self.assertTrue(first.isdisjoint(second))

    def test_reproducible_without_result_access_and_refuses_edits(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), forbid_result_access():
            root = Path(tmp)
            b.generate(root)
            manifest = root / "benchmark/manifest.csv"
            self.assertEqual(manifest.read_bytes(), (b.ROOT / "benchmark/manifest.csv").read_bytes())
            b.generate(root)
            row = b.read_manifest(manifest)[0]
            (root / "benchmark" / row["path"]).write_text("SELECT 1;")
            with self.assertRaisesRegex(ValueError, "Locally edited"):
                b.generate(root)





if __name__ == "__main__":
    unittest.main()
