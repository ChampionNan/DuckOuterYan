"""Frozen TPC-H promotion invariants; no database queries or performance runs."""
from collections import Counter
from pathlib import Path
import shutil
import tempfile
import unittest

import balanced_benchmark as b
from benchmark_corpus import resolve_sql_path
import tpch_tuning_promotion as promotion
import benchmark_plan_cohort as cohort
from test_gen_outerjoin_benchmark import forbid_result_access


class TpchPromotionTests(unittest.TestCase):
    def test_exact_frozen_members_and_preserved_slots(self):
        corpus = cohort.input_corpus()
        with forbid_result_access():
            rows = b.validate(corpus)
            original, old_paths, path_map = promotion.validate(corpus, rows)
        self.assertEqual(len(rows), 720)
        self.assertEqual(Counter(r["family"] for r in rows), promotion.policy()["expected_counts"])
        self.assertEqual(len(old_paths), 20)
        self.assertEqual(len(path_map), 20)
        old = {r["query_id"]: r for r in promotion.archived_rows()}
        current = {r["query_id"]: r for r in rows}
        for new in promotion.replacements():
            source = old[new["tuning_replaces_query_id"]]
            self.assertNotIn(source["query_id"], current)
            self.assertEqual((corpus / new["path"]).read_bytes(),
                             (promotion.CANDIDATES / new["path"]).read_bytes())
            self.assertEqual(resolve_sql_path(source["query_class"], source["path"]),
                             promotion.ARCHIVE / source["path"])
        for key in ("family", "tree_shape", "semantic_tier", "relation_count", "query_class"):
            self.assertEqual(Counter(r[key] for r in rows), Counter(r[key] for r in original))
        self.assertEqual(b.digest(promotion.ARCHIVE / "prior_manifest.csv"),
                         promotion.policy()["prior_manifest_sha256"])

    def test_regeneration_of_promoted_stage_needs_no_results(self):
        corpus = cohort.input_corpus()
        rows = b.read_manifest(corpus / "manifest.csv")
        original, old_paths, _ = promotion.validate(corpus, rows)
        with tempfile.TemporaryDirectory(prefix="tpch-promotion-test-") as tmp:
            stage = Path(tmp)
            (stage / "tpch").mkdir()
            for relative, source in old_paths.items():
                shutil.copyfile(source, stage / relative)
            (stage / "sample.txt").write_text("".join(p + "\n" for p in old_paths))
            with forbid_result_access():
                regenerated = promotion.apply(original, stage)
            self.assertEqual({r["query_id"] for r in regenerated}, {r["query_id"] for r in rows})
            for r in promotion.replacements():
                self.assertEqual(b.digest(stage / r["path"]), r["content_sha256"])
            self.assertFalse(set((stage / "sample.txt").read_text().splitlines()).intersection(old_paths))

    def test_validation_rejects_mutation_and_stale_query_list(self):
        corpus = cohort.input_corpus()
        with tempfile.TemporaryDirectory(prefix="tpch-promotion-test-") as tmp:
            stage = Path(tmp) / "benchmark"
            shutil.copytree(corpus, stage)
            rows = b.read_manifest(stage / "manifest.csv")
            source = promotion.archived_rows()[0]
            (stage / "stale.txt").write_text(source["path"] + "\n")
            with self.assertRaisesRegex(ValueError, "remains in query list"):
                promotion.validate(stage, rows)
            (stage / "stale.txt").unlink()
            candidate = promotion.replacements()[0]
            with (stage / candidate["path"]).open("a") as handle:
                handle.write("-- unexpected edit\n")
            with self.assertRaisesRegex(ValueError, "SQL changed"):
                promotion.validate(stage, rows)


if __name__ == "__main__":
    unittest.main()
