"""The two approved TPC-H predicate updates preserve unrelated workload slots."""
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

import balanced_benchmark as b
import tpch_selectivity_update as update
from test_gen_outerjoin_benchmark import forbid_result_access
from benchmark_test_fixtures import historical_corpus


class TpchSelectivityUpdateTest(unittest.TestCase):
    def test_only_two_predicates_and_original_bands(self):
        with forbid_result_access():
            corpus = historical_corpus(self)
            rows = b.validate(corpus)
            original, paths = update.validate(corpus, rows)
            changes = [(a, z) for a, z in zip(original, rows) if a != z]
            self.assertEqual(len(rows), 720)
            self.assertEqual(len(changes), 2)
            for old, new in changes:
                for key in ("query_id", "path", "family", "tree_shape", "relation_count", "semantic_tier", "join_vector"):
                    self.assertEqual(old[key], new[key])
                sql = (corpus / new["path"]).read_text()
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
                if generated["source_sha256"] != retained["source_sha256"]:
                    self.assertEqual(generated["source_location"], "auto_test/balanced_benchmark.py")
                    self.assertEqual(generated["source_sha256"], b.digest(Path(b.__file__)))
                    generated = dict(generated, source_sha256=retained["source_sha256"])
                self.assertEqual(generated, retained)
            for source in (b.ROOT / "benchmark").glob("*/*.sql"):
                self.assertEqual(source.read_bytes(),
                                 (root / "benchmark" / source.relative_to(b.ROOT / "benchmark")).read_bytes())

    def test_marker_and_sql_mutations_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "benchmark"
            shutil.copytree(historical_corpus(self), stage)
            rows = b.read_manifest(stage / "manifest.csv")
            (stage / update.MARKER).unlink()
            with self.assertRaisesRegex(ValueError, "marker missing"):
                update.validate(stage, rows)
            b.write_json(stage / update.MARKER, update.marker())
            sql = stage / update.policy()["replacements"][0]["original"]["path"]
            sql.write_text(sql.read_text().replace("1994-04-19", "1994-04-20"))
            with self.assertRaisesRegex(ValueError, "SQL changed"):
                update.validate(stage, rows)


if __name__ == "__main__":
    unittest.main()
