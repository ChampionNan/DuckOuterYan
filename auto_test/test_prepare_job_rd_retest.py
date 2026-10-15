import unittest
from unittest.mock import patch

import prepare_job_rd_retest as pilot
from test_gen_outerjoin_benchmark import forbid_result_access


class JobRightDeepPilotTest(unittest.TestCase):
    def test_predicates_only_and_fallback_is_not_acceptance(self):
        with forbid_result_access():
            entries = pilot.assemble()
        self.assertEqual(len(entries), 6)
        original = entries[0][1]
        for row, sql in entries:
            restored = sql.replace(row["selectivity_predicate"], "t.production_year >= 2008", 1)
            restored = restored.replace("-- selectivity: high;", "-- selectivity: medium;", 1)
            self.assertEqual(restored, original)
            self.assertEqual(row["qualification_min_speedup"], "0.7")
            self.assertEqual(row["qualification_status"], "PENDING_CPU9_MEASUREMENT")
        self.assertEqual([r["semantic_tier"] for r, _ in entries], ["medium"] + ["high"] * 5)

    def test_calibration_rejects_wrong_dataset_or_tier(self):
        for counts in ({"n": 1}, dict(n=2528312, **{"q" + str(i): 2528312 for i in range(6)})):
            with patch.object(pilot.common, "query_json", return_value=counts), self.assertRaises(ValueError):
                pilot.calibrate(None, None, pilot.assemble())


if __name__ == "__main__":
    unittest.main()
