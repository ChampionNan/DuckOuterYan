"""Timeout report values must never masquerade as measured paired runtimes."""
import unittest
import pandas as pd

import gen_experiment_result as plot
import refresh_paper_results as refresh


class TimeoutSubstitutionTests(unittest.TestCase):
    def row(self, **changes):
        return dict(dict(query="one", family="graph", run="one", selected_plan="OUTERYAN",
                         correct="NOT-CHECKED", correctness_check="disabled", timing_status="timeout",
                         duckdb_status="timeout", outeryan_status="measured", duckdb_timeout_seconds=600,
                         duckdb_timeout_stage="warmup", note="TIMEOUT-OFF-WARMUP", tm_off=float("nan"),
                         tm_on=.04, tm_speedup=float("nan")), **changes)

    def test_explicit_substitution_preserves_originals(self):
        source = pd.DataFrame([self.row()])
        view = refresh.apply_timeout_substitution(source)
        self.assertTrue(pd.isna(source.tm_off.iloc[0]))
        self.assertTrue(pd.isna(view.recorded_tm_off.iloc[0]))
        self.assertEqual(view.timing_status.iloc[0], "timeout")
        self.assertEqual(view.duckdb_timeout_stage.iloc[0], "warmup")
        detail = plot.prepare_queries(view, "tm")
        self.assertFalse(detail.valid_timing.iloc[0])
        self.assertTrue(detail.valid_speedup.iloc[0])
        self.assertEqual(detail.speedup.iloc[0], 15000)
        cohort, excluded = refresh.reporting_cohort(view)
        self.assertEqual(len(cohort), 1)
        self.assertTrue(excluded.empty)
        stats = plot.summarize(detail)
        self.assertEqual(stats["counts"]["measured"], 0)
        self.assertEqual(stats["counts"]["timeout_substituted"], 1)
        self.assertEqual(stats["totals"]["off_s"], 600)

    def test_failures_reverse_timeouts_and_invalid_times_are_not_substituted(self):
        for changes in (dict(outeryan_status="timeout"), dict(duckdb_status="measured"),
                        dict(tm_on=float("nan")), dict(tm_on=0), dict(tm_on=float("inf")),
                        dict(correct="FALSE"), dict(selected_plan="DUCKDB"),
                        dict(duckdb_timeout_seconds=900)):
            with self.subTest(changes=changes):
                view = refresh.apply_timeout_substitution(pd.DataFrame([self.row(**changes)]))
                self.assertFalse(plot.timeout_substitution_mask(view).any())

    def test_disabled_policy_and_ordinary_measurement(self):
        source = pd.DataFrame([self.row()])
        self.assertFalse(plot.prepare_queries(refresh.apply_timeout_substitution(source, 0), "tm").valid_speedup.any())
        source = pd.DataFrame([self.row(duckdb_status="measured", timing_status="measured",
                                        tm_off=2, tm_on=1, note="OK")])
        detail = plot.prepare_queries(refresh.apply_timeout_substitution(source), "tm")
        self.assertTrue(detail.valid_timing.iloc[0])
        self.assertEqual(detail.speedup.iloc[0], 2)


if __name__ == "__main__":
    unittest.main()
