"""The JOB adoption must preserve every unrelated SQL and survive regeneration."""
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

import balanced_benchmark as b
import job_selectivity_update as update
import benchmark_plan_cohort as cohort
from test_gen_outerjoin_benchmark import forbid_result_access


class JobSelectivityUpdateTest(unittest.TestCase):
    def test_single_predicate_and_slot(self):
        with forbid_result_access():
            rows = b.validate(b.ROOT / "benchmark")
            original, paths = update.validate(b.ROOT / "benchmark", rows)
            changes = [(a, z) for a, z in zip(original, rows) if a != z]
            expected_n = sum(cohort.policy()["expected_counts_after"].values()) if cohort.POLICY.exists() else 720
            self.assertEqual(len(rows), expected_n)
            self.assertEqual(len(changes), 1)
            old, new = changes[0]
            self.assertEqual(new["family"], "job")
            for field in ("query_id", "path", "tree_shape", "relation_count", "semantic_tier", "join_vector", "aggregate_variant"):
                self.assertEqual(old[field], new[field])
            sql = (b.ROOT / "benchmark" / new["path"]).read_text()
            self.assertEqual(sql.replace(new["selectivity_predicate"], old["selectivity_predicate"], 1),
                             paths[old["path"]].read_text())

    def test_regeneration_without_measurements(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()), forbid_result_access():
            root = Path(directory)
            b.generate(root)
            actual = b.read_manifest(root / "benchmark/manifest.csv")
            expected = b.read_manifest(b.ROOT / "benchmark/manifest.csv")
            self.assertEqual(len(actual), len(expected))
            for generated, retained in zip(actual, expected):
                # Graph seeds record the generator's hash. The generator now
                # includes JOB promotion, but their SQL must remain identical.
                if generated["source_sha256"] != retained["source_sha256"]:
                    self.assertEqual(generated["source_location"], "auto_test/balanced_benchmark.py")
                    self.assertEqual(generated["source_sha256"], b.digest(Path(b.__file__)))
                    generated = dict(generated, source_sha256=retained["source_sha256"])
                self.assertEqual(generated, retained)
            for source in (b.ROOT / "benchmark").glob("*/*.sql"):
                self.assertEqual(source.read_bytes(),
                                 (root / "benchmark" / source.relative_to(b.ROOT / "benchmark")).read_bytes())

    def test_missing_marker_and_mutation_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "benchmark"
            shutil.copytree(b.ROOT / "benchmark", stage)
            rows = b.read_manifest(stage / "manifest.csv")
            marker = stage / update.MARKER
            marker.unlink()
            with self.assertRaisesRegex(ValueError, "marker missing"):
                update.validate(stage, rows)
            b.write_json(marker, update.marker())
            sql = stage / update.policy()["original"]["path"]
            sql.write_text(sql.read_text().replace(">= 2011", ">= 2012"))
            with self.assertRaisesRegex(ValueError, "SQL changed"):
                update.validate(stage, rows)


if __name__ == "__main__":
    unittest.main()
