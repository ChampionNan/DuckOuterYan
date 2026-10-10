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


class GraphPromotionTests(unittest.TestCase):
    def test_active_promotion_and_reversible_sources(self):
        corpus = b.ROOT / "benchmark"
        rows = b.validate(corpus)
        before_extension, _ = extension.validate(corpus, rows)
        restored, paths = promotion.validate(corpus, before_extension)
        self.assertEqual(len(rows), 722)
        self.assertEqual(len(restored), 723)
        self.assertEqual(len(paths), 16)
        self.assertEqual(Counter(r["graph_dataset"] for r in rows if r["family"] == "graph"),
                         {"bitcoin": 156, "epinions": 18})
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
        self.assertEqual(counts, {"bitcoin": 156, "epinions": 18})

    def test_three_extensions_preserve_structure_and_are_pinned(self):
        corpus = b.ROOT / "benchmark"
        rows = b.validate(corpus)
        restored, paths = extension.validate(corpus, rows)
        self.assertEqual(len(paths), 3)
        for row in extension.candidates():
            self.assertEqual((corpus / row["path"]).read_bytes(), (extension.CANDIDATES / row["path"]).read_bytes())
            self.assertFalse((corpus / ("graph/" + row["graph_dataset_source_query"] + ".sql")).exists())
        self.assertEqual(Counter(r["graph_dataset"] for r in restored if r["family"] == "graph"),
                         {"bitcoin": 159, "epinions": 15})

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
