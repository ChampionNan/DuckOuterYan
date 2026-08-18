#!/usr/bin/env python3

import importlib.util
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
import matplotlib.pyplot as plt


PLOT_PATH = Path(__file__).with_name("plot_speedup.py")
SPEC = importlib.util.spec_from_file_location("plot_speedup", PLOT_PATH)
PLOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLOT)


def result_frame(rows):
    return pd.DataFrame(
        rows,
        columns=["query", "family", "t1_speedup", "tm_speedup", "marker"],
    )


class PlotSpeedupLoadTest(unittest.TestCase):
    def test_result_source_normalizes_attempts_suffix(self):
        final = "experiment_onoff_20260810_120000.csv"
        attempts = "experiment_onoff_20260810_120000.attempts.csv"
        self.assertEqual(PLOT.result_source(final), ("20260810_120000", "final"))
        self.assertEqual(PLOT.result_source(attempts), ("20260810_120000", "attempts"))

    def test_same_timestamp_merges_with_final_precedence(self):
        attempts_path = "experiment_onoff_20260810_120000.attempts.csv"
        final_path = "experiment_onoff_20260810_120000.csv"
        sources = {
            attempts_path: result_frame([
                ("oy_th_th_line3_v0", "tpch", 1.1, 1.2, "attempt"),
                ("oy_th_th_line3_v1", "tpch", 1.3, 1.4, "attempt-only"),
            ]),
            final_path: result_frame([
                ("oy_th_th_line3_v0", "tpch", 2.1, 2.2, "final"),
            ]),
        }

        with mock.patch.object(PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()):
            # Final precedence must not depend on argument order.
            loaded = PLOT.load([final_path, attempts_path])

        self.assertEqual(set(loaded["query"]), {"oy_th_th_line3_v0", "oy_th_th_line3_v1"})
        self.assertEqual(loaded["run"].unique().tolist(), ["20260810_120000"])
        by_query = loaded.set_index("query")
        self.assertEqual(by_query.loc["oy_th_th_line3_v0", "marker"], "final")
        self.assertEqual(by_query.loc["oy_th_th_line3_v1", "marker"], "attempt-only")

    def test_empty_final_keeps_attempt_rows(self):
        attempts_path = "experiment_onoff_20260810_130000.attempts.csv"
        final_path = "experiment_onoff_20260810_130000.csv"
        attempts = result_frame([
            ("oy_ds_ds_line3_v0", "tpcds", 0.9, 1.0, "attempt-only"),
        ])

        def read_csv(path):
            if path == final_path:
                raise pd.errors.EmptyDataError("No columns to parse from file")
            return attempts.copy()

        with mock.patch.object(PLOT.pd, "read_csv", side_effect=read_csv):
            loaded = PLOT.load([attempts_path, final_path])

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded.iloc[0]["run"], "20260810_130000")
        self.assertEqual(loaded.iloc[0]["marker"], "attempt-only")

    def test_historical_rows_without_family_still_merge(self):
        attempts_path = "experiment_onoff_20260810_140000.attempts.csv"
        final_path = "experiment_onoff_20260810_140000.csv"
        columns = ["query", "t1_speedup", "tm_speedup", "marker"]
        sources = {
            attempts_path: pd.DataFrame([
                ("oy_jb_jb_line3_v0", 1.0, 1.1, "attempt"),
            ], columns=columns),
            final_path: pd.DataFrame([
                ("oy_jb_jb_line3_v0", 1.2, 1.3, "final"),
            ], columns=columns),
        }

        with mock.patch.object(PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()):
            loaded = PLOT.load([attempts_path, final_path])

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded.iloc[0]["family"], "JOB")
        self.assertEqual(loaded.iloc[0]["marker"], "final")

    def test_reported_family_is_used_for_new_benchmark_names(self):
        frame = result_frame([
            ("ojb_sqlstorm_tpch_15031_ldmx", "tpch", 1.1, 1.2, "final"),
        ])
        loaded = PLOT.enrich(frame, "20260816_120000")
        self.assertEqual(loaded.iloc[0]["family"], "TPC-H")

    def test_legacy_cleanup_preserves_non_figure_files(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / "old.pdf").write_text("generated")
            (directory / "old.png").write_text("generated")
            (directory / "notes.txt").write_text("keep")

            self.assertEqual(PLOT.clear_generated_figures(directory), 2)
            self.assertFalse((directory / "old.pdf").exists())
            self.assertFalse((directory / "old.png").exists())
            self.assertTrue((directory / "notes.txt").exists())

    def test_phase_breakdown_includes_duckdb_baseline(self):
        frame = pd.DataFrame([{
            "query": "ojb_tpch_q5_ldmx",
            "family": "TPC-H",
            "selected_plan": "OUTERYAN",
            "profile_round1_operator_s": 1.0,
            "profile_round2_operator_s": 2.0,
            "profile_round3_operator_s": 3.0,
            "profile_other_elapsed_s": 4.0,
            "profile_threads": 8,
            "profile_total_time_s": 2.0,
            "profile_cpu_time_s": 10.0,
            "profile_round1_ratio": 0.1,
            "profile_round2_ratio": 0.2,
            "profile_round3_ratio": 0.3,
            "profile_other_ratio": 0.4,
            "tm_off": 3.0,
            "t1_off": 99.0,
        }])

        captured = []
        with mock.patch.object(PLOT, "save", side_effect=lambda fig, *_: captured.append(fig)):
            PLOT.fig_phase_by_family(frame, "unused")

        self.assertEqual(len(captured), 1)
        labels = [text.get_text() for text in captured[0].legends[0].get_texts()]
        self.assertIn(PLOT.OUTERYAN_TOTAL_LABEL, labels)
        self.assertIn(PLOT.BASELINE_LABEL, labels)
        annotation_text = [text.get_text() for text in captured[0].axes[0].texts]
        self.assertFalse(any("OuterYan" in text or "DuckDB" in text
                             for text in annotation_text))
        baseline_bar = captured[0].axes[0].patches[-1]
        baseline_endpoint = baseline_bar.get_x() + baseline_bar.get_width()
        self.assertTrue(math.isclose(baseline_endpoint, 3.0))
        self.assertFalse(captured[0].axes[0].spines["top"].get_visible())
        self.assertFalse(captured[0].axes[0].spines["right"].get_visible())
        plt.close(captured[0])

    def test_phase_breakdown_legacy_row_uses_t1_baseline(self):
        frame = pd.DataFrame([{
            "query": "ojb_tpch_q5_ldmx",
            "family": "TPC-H",
            "selected_plan": "OUTERYAN",
            "profile_round1_operator_s": 1.0,
            "profile_round2_operator_s": 2.0,
            "profile_round3_operator_s": 3.0,
            "profile_other_elapsed_s": 4.0,
            "profile_total_time_s": 10.0,
            "profile_round1_ratio": 0.1,
            "profile_round2_ratio": 0.2,
            "profile_round3_ratio": 0.3,
            "profile_other_ratio": 0.4,
            "t1_off": 12.0,
            "tm_off": 99.0,
        }])

        captured = []
        with mock.patch.object(PLOT, "save", side_effect=lambda fig, *_: captured.append(fig)):
            PLOT.fig_phase_by_family(frame, "unused")

        self.assertEqual(len(captured), 1)
        baseline_bar = captured[0].axes[0].patches[-1]
        baseline_endpoint = baseline_bar.get_x() + baseline_bar.get_width()
        self.assertTrue(math.isclose(baseline_endpoint, 12.0))
        plt.close(captured[0])


if __name__ == "__main__":
    unittest.main()
