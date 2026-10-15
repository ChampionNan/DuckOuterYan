"""The isolated pilot may change two WHERE predicates, never the active corpus."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_slow_pair_retest as pilot
from benchmark_test_fixtures import historical_corpus


class SlowPairPilotTest(unittest.TestCase):
    def setUp(self):
        self.corpus = historical_corpus(self, "before_job")

    def test_only_two_frozen_sources_and_predicates_change(self):
        before = pilot.digest(self.corpus / "manifest.csv")
        entries = pilot.assemble(self.corpus)
        _, archived = pilot.source_snapshot(self.corpus)
        self.assertEqual(len(entries), 8)
        self.assertEqual(len({row["path"] for row, _ in entries}), 8)
        for row, sql in entries:
            relative = row["family"] + "/" + row["pilot_source_query"] + ".sql"
            original = archived.get(relative, self.corpus / relative)
            source = original.read_text()
            predicate = "t.production_year >= 2008" if row["family"] == "job" else (
                "orders.o_orderdate BETWEEN DATE '1994-03-20' AND DATE '1996-03-09'")
            self.assertEqual(sql.replace(row["selectivity_predicate"], predicate, 1), source)
            self.assertEqual(row["content_sha256"], hashlib.sha256(sql.encode()).hexdigest())
            self.assertEqual(row["semantic_tier"], "medium")
            if row["pilot_role"] == "candidate":
                self.assertEqual(row["calibration_fraction"], "")
        self.assertEqual(pilot.digest(self.corpus / "manifest.csv"), before)

    def test_frozen_manifest_is_required(self):
        with mock.patch.object(pilot, "digest", return_value="different"):
            # A non-restorable manifest still fails even after JOB promotion.
            with mock.patch.object(pilot, "MANIFEST_SHA", "not-a-real-hash"):
                with self.assertRaisesRegex(ValueError, "manifest changed"):
                    pilot.assemble(self.corpus)

    def test_fresh_output_has_complete_provenance_and_does_not_overwrite(self):
        entries = pilot.assemble(self.corpus)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pilot"
            pilot.materialize(output, entries, {"local_only": True})
            self.assertEqual(len((output / "queries.txt").read_text().splitlines()), 8)
            for row, sql in entries:
                self.assertEqual((output / row["path"]).read_text(), sql)
            with self.assertRaises(FileExistsError):
                pilot.materialize(output, entries, {})


if __name__ == "__main__":
    unittest.main()
