"""A-H-B-07 candidates must preserve the entire query except its date predicate."""
from datetime import date
from pathlib import Path
import unittest
from unittest import mock

import prepare_ahb07_retest as pilot
from benchmark_test_fixtures import historical_corpus


class Ahb07RetestTest(unittest.TestCase):
    def setUp(self):
        self.corpus = historical_corpus(self)

    def test_launcher_uses_query_list_scope(self):
        script = Path(__file__).with_name("run_ahb07_retest.sh").read_text()
        self.assertIn('--only all --query-list "$OY_CORPUS/queries.txt"', script)
        self.assertIn('--threads 32 --runs 5 --timeout 600', script)

    def test_frozen_shape_and_only_date_windows(self):
        entries = pilot.assemble(self.corpus)
        original, source = entries[0]
        self.assertEqual(len(entries), 7)
        self.assertEqual(len({r["sql_fingerprint"] for r, _ in entries}), 7)
        for row, sql in entries:
            self.assertEqual(sql.replace(row["selectivity_predicate"], original["selectivity_predicate"], 1), source)
            self.assertEqual(row["semantic_tier"], "high")
            for key in ("source_seed", "tree_shape", "join_vector", "relation_count", "aggregate_variant"):
                self.assertEqual(row[key], original[key])
        for _, start, _ in pilot.WINDOWS:
            self.assertLessEqual(date.fromisoformat(start), date(1994, 1, 1))

    def test_stale_sql_is_rejected(self):
        with mock.patch.object(pilot.common, "digest", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "source changed"):
                pilot.assemble(self.corpus)

    def test_scale_mismatch_fails_before_calibration(self):
        with mock.patch.object(pilot.common, "query_json", return_value={"orders": 1500000, "customer": 150000}):
            with self.assertRaisesRegex(ValueError, "scale mismatch"):
                pilot.calibrate(None, None, pilot.assemble(self.corpus), 50)


if __name__ == "__main__":
    unittest.main()
