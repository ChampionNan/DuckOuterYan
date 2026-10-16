"""Bounded metadata/routing tests; no benchmark query executions."""
import csv
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import balanced_benchmark as b
import graph_dataset_promotion as promotion
import graph_dataset_extension as extension
import benchmark_plan_cohort as cohort
from benchmark_corpus import resolve_sql_path


class GraphPromotionTests(unittest.TestCase):
    def test_active_promotion_and_reversible_sources(self):
        corpus = cohort.input_corpus()
        rows = b.validate(corpus)
        before_extension, _ = extension.validate(corpus, rows)
        restored, paths = promotion.validate(corpus, before_extension)
        self.assertEqual(len(rows), 720)
        self.assertEqual(len(restored), 723)
        self.assertEqual(len(paths), 16)
        summary = json.loads((corpus / "design_summary.json").read_text())
        self.assertEqual(summary["graph_relation_counts"], {"4": 121, "5": 51})
        self.assertEqual(Counter(r["graph_dataset"] for r in rows if r["family"] == "graph"),
                         {"bitcoin": 156, "epinions": 16})
        old = {r["query_id"] for r in promotion.archived_rows()}
        self.assertTrue(old.isdisjoint(r["query_id"] for r in rows))
        self.assertTrue(old.issubset(r["query_id"] for r in restored))
        for row in promotion.candidates():
            if row["query_id"] == promotion.RETIRED_QUERY:
                self.assertFalse((corpus / row["path"]).exists())
                continue
            self.assertEqual((corpus / row["path"]).read_bytes(),
                             (promotion.CANDIDATES / row["path"]).read_bytes())

    def test_each_graph_query_routes_by_manifest(self):
        corpus = b.ROOT / "benchmark"
        counts = Counter(promotion.query_dataset(corpus, r["path"])
                         for r in b.read_manifest(corpus / "manifest.csv") if r["family"] == "graph")
        self.assertEqual(counts, {"bitcoin": 61, "epinions": 6} if cohort.POLICY.exists()
                         else {"bitcoin": 156, "epinions": 16})

    def test_three_extensions_preserve_structure_and_are_pinned(self):
        corpus = cohort.input_corpus()
        rows = b.validate(corpus)
        restored, paths = extension.validate(corpus, rows)
        self.assertEqual(len(paths), 3)
        for row in extension.candidates():
            if row["query_id"] in extension.retired_queries():
                self.assertFalse((corpus / row["path"]).exists())
                self.assertEqual(b.digest(extension.CANDIDATES / row["path"]), row["content_sha256"])
                self.assertEqual(resolve_sql_path(row["query_class"], row["path"]), extension.CANDIDATES / row["path"])
            else:
                self.assertEqual((corpus / row["path"]).read_bytes(), (extension.CANDIDATES / row["path"]).read_bytes())
            self.assertFalse((corpus / ("graph/" + row["graph_dataset_source_query"] + ".sql")).exists())
        self.assertEqual(Counter(r["graph_dataset"] for r in restored if r["family"] == "graph"),
                         {"bitcoin": 159, "epinions": 15})

    def test_timeout_retirements_are_exact_and_remain_excluded_on_regeneration(self):
        corpus = cohort.input_corpus()
        rows = b.validate(corpus)
        retired = extension.retired_queries()
        ids = {r["query_id"] for r in rows}
        self.assertTrue(retired.isdisjoint(ids))
        for row in extension.candidates():
            if row["query_id"] not in retired:
                continue
            for tier in ("medium", "high"):
                self.assertIn(row["graph_dataset_source_query"].replace("__sel_low", "__sel_" + tier), ids)
        restored, paths = extension.validate(corpus, rows)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "graph").mkdir()
            for relative, source in paths.items():
                shutil.copyfile(source, output / relative)
            old_paths = list(paths)
            (output / "query_list.txt").write_text("\n".join(old_paths) + "\n")
            regenerated = extension.apply(restored, output)
            self.assertEqual({r["query_id"] for r in regenerated}, ids)
            listed = (output / "query_list.txt").read_text().splitlines()
            self.assertEqual(len(listed), 1)
            for row in extension.candidates():
                self.assertEqual((output / row["path"]).exists(), row["query_id"] not in retired)

    def test_timeout_retirement_validator_rejects_stale_query_lists(self):
        corpus = cohort.input_corpus()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark"
            shutil.copytree(corpus, output)
            row = next(r for r in extension.candidates() if r["query_id"] in extension.retired_queries())
            (output / "stale.txt").write_text(row["path"] + "\n")
            with self.assertRaisesRegex(ValueError, "remains in query list"):
                extension.validate(output, b.read_manifest(output / "manifest.csv"))

    def test_routing_rejects_missing_and_edited_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp)
            row = promotion.candidates()[0]
            path = corpus / row["path"]
            path.parent.mkdir()
            shutil.copyfile(promotion.CANDIDATES / row["path"], path)
            b.write_csv(corpus / "manifest.csv", [row])
            self.assertEqual(promotion.query_dataset(corpus, row["path"]), "epinions")
            with self.assertRaisesRegex(ValueError, "absent or duplicated"):
                promotion.query_dataset(corpus, "graph/missing.sql")
            path.write_text(path.read_text() + "-- changed\n")
            with self.assertRaisesRegex(ValueError, "does not match"):
                promotion.query_dataset(corpus, row["path"])

    def test_unmanaged_corpus_retains_explicit_dataset_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(promotion.query_dataset(Path(tmp), "graph/one.sql", "wiki"), "wiki")

    def test_no_outcome_based_filter_is_added(self):
        self.assertEqual(promotion.marker()["replaced_queries"], 16)
        self.assertIn("including timeout and fallback", promotion.marker()["policy"])
        text = Path(promotion.__file__).read_text()
        self.assertNotIn("csv.DictReader", text)
        self.assertNotIn("tm_speedup", text)


if __name__ == "__main__":
    unittest.main()
