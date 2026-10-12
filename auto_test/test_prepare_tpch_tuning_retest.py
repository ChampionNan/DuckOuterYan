"""Guards for the isolated full TPC-H pilot; no database needed."""
import tempfile
from pathlib import Path
import unittest

import prepare_tpch_tuning_retest as pilot


class FullTpchPilotTests(unittest.TestCase):
    def test_complete_tpch_snapshot_without_promotion(self):
        before = pilot.digest(pilot.ACTIVE / "manifest.csv")
        spec, candidates, inputs = pilot.validate_inputs()
        self.assertEqual(len(inputs), 176)
        self.assertEqual(len(candidates), 31)
        candidate_ids = {r["query_id"] for r in candidates}
        self.assertEqual(sum(r["query_id"] in candidate_ids for r, _ in inputs), 31)
        self.assertTrue(all(r["family"] == "tpch" for r, _ in inputs))
        with tempfile.TemporaryDirectory(prefix="tpch-full-pilot-test-") as work:
            output = Path(work) / "corpus"
            pilot.materialize(output, inputs, spec)
            records = pilot.rows(output / "manifest.csv")
            self.assertEqual(len(records), 176)
            self.assertEqual(len(list(output.rglob("*.sql"))), 176)
            self.assertEqual((output / "queries.txt").read_text().splitlines(),
                             [r["path"] for r in records])
            self.assertEqual(len({r["corpus_revision"] for r in records}), 1)
            for row in records:
                self.assertEqual(pilot.digest(output / row["path"]), row["content_sha256"])
            with self.assertRaises(FileExistsError):
                pilot.materialize(output, inputs, spec)
        self.assertEqual(pilot.digest(pilot.ACTIVE / "manifest.csv"), before)


if __name__ == "__main__":
    unittest.main()
