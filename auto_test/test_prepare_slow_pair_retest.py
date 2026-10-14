"""The isolated pilot may change two WHERE predicates, never the active corpus."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_slow_pair_retest as pilot


class SlowPairPilotTest(unittest.TestCase):
    def test_only_two_frozen_sources_and_predicates_change(self):
        before = pilot.digest(pilot.ACTIVE / "manifest.csv")
        entries = pilot.assemble()
        self.assertEqual(len(entries), 8)
        self.assertEqual(len({row["path"] for row, _ in entries}), 8)
        for row, sql in entries:
            original = pilot.ACTIVE / row["family"] / (row["pilot_source_query"] + ".sql")
            source = original.read_text()
            predicate = "t.production_year >= 2008" if row["family"] == "job" else (
                "orders.o_orderdate BETWEEN DATE '1994-03-20' AND DATE '1996-03-09'")
            self.assertEqual(sql.replace(row["selectivity_predicate"], predicate, 1), source)
            self.assertEqual(row["content_sha256"], hashlib.sha256(sql.encode()).hexdigest())
            self.assertEqual(row["semantic_tier"], "medium")
            if row["pilot_role"] == "candidate":
                self.assertEqual(row["calibration_fraction"], "")
        self.assertEqual(pilot.digest(pilot.ACTIVE / "manifest.csv"), before)

    def test_frozen_manifest_is_required(self):
        with mock.patch.object(pilot, "digest", return_value="different"):
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                pilot.assemble()

    def test_fresh_output_has_complete_provenance_and_does_not_overwrite(self):
        entries = pilot.assemble()
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
