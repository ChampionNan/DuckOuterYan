"""No automatic promotion, honest selectivity labels and unchanged SQL structure."""
from collections import Counter
import csv
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import prepare_slow_three_retest as pilot
from benchmark_test_fixtures import historical_corpus


class SlowThreeTest(unittest.TestCase):
    def setUp(self):
        self.corpus = historical_corpus(self)

    def test_predicate_only_and_band_labels(self):
        before = pilot.common.digest(self.corpus / "manifest.csv")
        with (self.corpus / "manifest.csv").open() as handle:
            originals = {r["query_id"]: r for r in csv.DictReader(handle)}
        entries = pilot.assemble(self.corpus)
        self.assertEqual(len(entries), 16)
        self.assertEqual(Counter(r["pilot_short_id"] for r, _ in entries),
                         {"A-H-B-07": 7, "A-J-RD-05": 7, "A-J-B-07": 2})
        self.assertEqual(Counter(r["pilot_role"] for r, _ in entries), {"original_control": 3, "candidate": 13})
        self.assertEqual(len({r["sql_fingerprint"] for r, _ in entries}), 16)
        for row, sql in entries:
            original = originals[row["pilot_source_query"]]
            self.assertEqual(sql.replace(row["selectivity_predicate"], original["selectivity_predicate"], 1),
                             (self.corpus / original["path"]).read_text())
            self.assertEqual(row["content_sha256"], hashlib.sha256(sql.encode()).hexdigest())
            for key in ("family", "source_seed", "tree_shape", "join_vector", "relation_count", "aggregate_variant"):
                self.assertEqual(row[key], original[key])
            self.assertIn("__sel_" + row["semantic_tier"] + "__", row["query_id"])
            self.assertEqual(row["selectivity_tier"], "sel_" + row["semantic_tier"])
        self.assertEqual(pilot.common.digest(self.corpus / "manifest.csv"), before)

    def test_changed_sources_rejected(self):
        with mock.patch.object(pilot.common, "digest", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "source SQL changed"):
                pilot.assemble(self.corpus)

    def test_scale_and_band_checks(self):
        with mock.patch.object(pilot.common, "query_json", return_value={"orders": 1500000, "customer": 150000}):
            with self.assertRaisesRegex(ValueError, "scale mismatch"):
                pilot.common.calibrate(None, {"tpch": None, "job": None}, pilot.assemble(self.corpus), 50)
        counts = {"orders": 75000000, "customer": 7500000}
        with mock.patch.object(pilot.common, "query_json", side_effect=[counts, {"n": 100, "q0": 90}]):
            with self.assertRaisesRegex(ValueError, "left the source band"):
                pilot.common.calibrate(None, {"tpch": None, "job": None}, pilot.assemble(self.corpus), 50)

    def test_materialization_and_launcher(self):
        entries = pilot.assemble(self.corpus)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pilot"
            pilot.common.materialize(output, entries, {})
            self.assertEqual(len((output / "queries.txt").read_text().splitlines()), 16)
            with self.assertRaises(FileExistsError):
                pilot.common.materialize(output, entries, {})
        launcher = Path(__file__).with_name("run_slow_three_retest.sh").read_text()
        self.assertIn('--only all --query-list "$OY_CORPUS/queries.txt"', launcher)
        self.assertIn('--threads 32 --runs 5 --timeout 600', launcher)
        self.assertIn('--tpch-sf 50', launcher)
        self.assertIn('--no-check-correctness', launcher)


if __name__ == "__main__":
    unittest.main()
