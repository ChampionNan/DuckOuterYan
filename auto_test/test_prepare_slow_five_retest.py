"""Five slow slots only; SQL edits are confined to their original predicates."""
from collections import Counter
import csv
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_slow_five_retest as pilot


class SlowFiveTest(unittest.TestCase):
    def test_fixed_slots_and_only_predicate_changes(self):
        before = pilot.digest(pilot.ACTIVE / "manifest.csv")
        with (pilot.ACTIVE / "manifest.csv").open() as handle:
            originals = {r["query_id"]: r for r in csv.DictReader(handle)}
        entries = pilot.assemble()
        self.assertEqual(len(entries), 20)
        self.assertEqual(Counter(r["pilot_short_id"] for r, _ in entries), {s[0]: 4 for s in pilot.SPECS})
        self.assertEqual(Counter(r["pilot_role"] for r, _ in entries), {"original_control": 5, "candidate": 15})
        self.assertEqual(len({r["sql_fingerprint"] for r, _ in entries}), 20)
        for row, sql in entries:
            original = originals[row["pilot_source_query"]]
            source = (pilot.ACTIVE / original["path"]).read_text()
            self.assertEqual(sql.replace(row["selectivity_predicate"], original["selectivity_predicate"], 1), source)
            self.assertEqual(row["content_sha256"], hashlib.sha256(sql.encode()).hexdigest())
            for field in ("family", "source_seed", "tree_shape", "join_vector", "relation_count",
                          "aggregate_variant", "semantic_tier", "target_min_fraction", "target_max_fraction"):
                self.assertEqual(row[field], original[field])
            self.assertEqual(row["calibration_fraction"], "")
        self.assertEqual(pilot.digest(pilot.ACTIVE / "manifest.csv"), before)

    def test_stale_source_is_rejected(self):
        with mock.patch.object(pilot, "digest", return_value="modified"):
            with self.assertRaisesRegex(ValueError, "source SQL changed"):
                pilot.assemble()

    def test_materialized_inputs_reproduce_without_overwriting(self):
        entries = pilot.assemble()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pilot"
            pilot.materialize(output, entries, {"test": True})
            self.assertEqual(len((output / "queries.txt").read_text().splitlines()), 20)
            for row, sql in entries:
                self.assertEqual((output / row["path"]).read_text(), sql)
            with self.assertRaises(FileExistsError):
                pilot.materialize(output, entries, {})


if __name__ == "__main__":
    unittest.main()
