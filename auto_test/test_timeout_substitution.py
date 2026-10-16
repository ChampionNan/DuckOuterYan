"""Legacy complete-pair reports exclude timeouts; capped cohorts have separate tests."""
import unittest
from unittest.mock import patch
import pandas as pd

import gen_experiment_result as plot


class TimeoutExclusionTests(unittest.TestCase):
    def setUp(self):
        cutoff = patch.object(plot, "MIN_RUNTIME_SECONDS", 0.0)
        cutoff.start()
        self.addCleanup(cutoff.stop)

    def row(self, **changes):
        return dict(dict(query="one", family="graph", run="one", selected_plan="OUTERYAN",
                         correct="NOT-CHECKED", correctness_check="disabled", timing_status="measured",
                         timing_threads=32, duckdb_status="measured", outeryan_status="measured",
                         duckdb_timeout_seconds=600, duckdb_timeout_stage="-", outeryan_timeout_stage="-",
                         note="OK", tm_off=2.0, tm_on=.04, tm_speedup=50.0), **changes)

    def test_default_preserves_partial_times_but_excludes_the_query(self):
        source = pd.DataFrame([self.row(duckdb_status="timeout", timing_status="timeout",
                                       duckdb_timeout_stage="warmup", tm_off=float("nan"))])
        self.assertTrue(pd.isna(source.tm_off.iloc[0]))
        self.assertEqual(source.tm_on.iloc[0], .04)
        detail = plot.prepare_queries(source, "tm")
        self.assertFalse(detail.valid_timing.any())
        self.assertFalse(detail.valid_speedup.any())
        self.assertTrue(detail.speedup.isna().all())
        self.assertTrue(plot.complete_runtime_rows(source).empty)
        stats = plot.summarize(detail)
        self.assertEqual(stats["counts"]["timeout_substituted"], 0)
        self.assertIsNone(stats["totals"]["off_s"])

    def test_each_timeout_signal_excludes_even_finite_pairs_without_notes(self):
        signals = [dict(duckdb_status="timeout"), dict(outeryan_status="TIMEOUT"),
                   dict(timing_status="timeout"), dict(correct="TIMEOUT"), dict(note="TIMEOUT-ON-KERNEL"),
                   dict(duckdb_correctness_status="timeout"), dict(outeryan_correctness_status="timeout"),
                   dict(profile_status="timeout"), dict(optimizer_profile_status="timeout"),
                   dict(runtime_treatment="duckdb_timeout_600s")]
        for side in ("duckdb", "outeryan"):
            signals.extend({side + "_timeout_stage": stage}
                           for stage in ("correctness", "warmup", "kernel", "profile", "timing"))
        for signal in signals:
            with self.subTest(signal=signal):
                frame = pd.DataFrame([self.row(**signal)])
                detail = plot.prepare_queries(frame, "tm")
                self.assertFalse(detail.valid_speedup.any())
                self.assertEqual(detail.exclusion_reason.tolist(), ["timeout"])
                self.assertTrue(plot.complete_runtime_rows(frame).empty)
                self.assertTrue(plot.selected_runtime_rows(frame).empty)
                self.assertTrue(plot.positive_runtime_rows(frame, "tm").empty)

    def test_status_only_timeouts_also_exclude_phase_and_optimizer_profiles(self):
        profile = dict(
            profile_status="OK", profile_threads=32, profile_wall_time_s=.04,
            profile_cpu_time_s=10, profile_round1_operator_s=1,
            profile_round2_operator_s=2, profile_round3_operator_s=3,
            profile_other_elapsed_s=4, optimizer_profile_status="OK",
            optimizer_duckdb_total_s=.001, optimizer_outeryan_total_s=.002,
            optimizer_duckdb_phases_json='{"join_reorder": 0.001}',
            optimizer_outeryan_phases_json='{"join_reorder": 0.002}',
        )
        base = pd.DataFrame([self.row(**profile)])
        self.assertTrue(plot.build_phase_statistics(base, "tm")["available"])
        self.assertTrue(plot.build_optimizer_statistics(base)["available"])
        for side in ("duckdb", "outeryan"):
            for signal in ({side + "_status": "timeout"}, {side + "_timeout_stage": "warmup"}):
                with self.subTest(signal=signal):
                    frame = pd.DataFrame([self.row(**profile, **signal)])
                    self.assertFalse(plot.build_phase_statistics(frame, "tm")["available"])
                    self.assertFalse(plot.build_optimizer_statistics(frame)["available"])

    def test_legacy_capped_export_cannot_reenter_statistics(self):
        legacy = pd.DataFrame([self.row(runtime_treatment="duckdb_timeout_600s", tm_off=600,
                                       duckdb_status="timeout", timing_status="timeout")])
        self.assertTrue(plot.timeout_substitution_mask(legacy).all())
        self.assertFalse(plot.prepare_queries(legacy, "tm").valid_speedup.any())
        self.assertTrue(plot.complete_runtime_rows(legacy).empty)

    def test_timeout_limit_alone_does_not_mean_timeout(self):
        frame = pd.DataFrame([self.row(tm_off=600, tm_on=2)])
        self.assertFalse(plot.timeout_mask(frame).any())
        detail = plot.prepare_queries(frame, "tm")
        self.assertTrue(detail.valid_timing.all())
        self.assertEqual(detail.speedup.iloc[0], 300)

    def test_subsecond_measurements_and_slowdowns_remain(self):
        frame = pd.DataFrame([self.row(tm_off=.02, tm_on=.04)])
        detail = plot.prepare_queries(frame, "tm")
        self.assertTrue(detail.valid_speedup.all())
        self.assertEqual(detail.speedup.iloc[0], .5)


if __name__ == "__main__":
    unittest.main()
