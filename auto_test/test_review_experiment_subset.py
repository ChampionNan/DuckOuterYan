import unittest

import review_experiment_subset as review


class ReviewSubsetTest(unittest.TestCase):
    def test_exact_boundaries_and_unrounded_ratio(self):
        frame = review.pd.DataFrame({
            "query": ["a", "b", "c", "d", "e", "f"],
            "family": ["tpch"] * 6,
            "correct": ["TRUE"] * 6,
            "tm_off": [1.0, 2.0, .99, 5.0, 1.1999, 1.0],
            "tm_on": [1.25, .5, 2.0, 10.0, 1.5, 1.0],
            "tm_speedup": [.8, 4, .5, .5, .8, 1],
        })
        detail, stages = review.classify(frame)
        self.assertEqual(detail.loc[stages["review_speedup_filtered"], "query"].tolist(), ["a", "f"])
        self.assertEqual(detail.review_status.tolist(), [
            "retained", "either_runtime_below_threshold", "either_runtime_below_threshold",
            "speedup_below_threshold", "speedup_below_threshold", "retained"])

    def test_unmeasured_and_invalid_never_enter(self):
        frame = review.pd.DataFrame({
            "query": ["fallback", "timeout", "wrong", "missing"], "family": ["job"] * 4,
            "correct": ["TRUE", "TRUE", "FALSE", "TRUE"],
            "note": ["FALLBACK-SKIP", "TIMEOUT", "", ""],
            "tm_off": [2, 2, 2, float("nan")], "tm_on": [2, 2, 2, 2],
        })
        detail, stages = review.classify(frame)
        self.assertFalse(stages["complete_measured_pairs"].any())
        self.assertEqual(detail.review_status.tolist(), ["fallback_not_executed", "timeout",
                                                        "correctness_not_true", "missing_or_invalid_timing"])


if __name__ == "__main__":
    unittest.main()
