#!/usr/bin/env python3

import importlib.util
import math
import unittest
from pathlib import Path
from unittest import mock

import matplotlib.pyplot as plt
import pandas as pd


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
    def test_result_source_groups_components_by_timestamp(self):
        self.assertEqual(
            PLOT.result_source("experiment_onoff_core_20260818_011114.csv"),
            ("20260818_011114", "final", "core"),
        )
        self.assertEqual(
            PLOT.result_source(
                "experiment_onoff_industry_inspired_20260818_011114.attempts.csv"
            ),
            ("20260818_011114", "attempts", "industry_inspired"),
        )
        self.assertEqual(
            PLOT.result_source("experiment_onoff_20260810_120000.csv"),
            ("20260810_120000", "final", "legacy"),
        )

    def test_same_timestamp_unifies_core_and_industry(self):
        core_path = "experiment_onoff_core_20260818_011114.csv"
        industry_path = "experiment_onoff_industry_inspired_20260818_011114.csv"
        sources = {
            core_path: result_frame([
                ("ojb_tpch_q08_market_share_ldmx", "tpch", 1.1, 1.2, "derived"),
            ]),
            industry_path: result_frame([
                ("oy_th_real_supplier_right", "tpch", 1.3, 1.4, "industry"),
            ]),
        }
        with mock.patch.object(PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()):
            loaded = PLOT.load([core_path, industry_path])

        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded["run"].unique().tolist(), ["20260818_011114"])
        classes = loaded.set_index("query")["query_class"].to_dict()
        self.assertEqual(classes["ojb_tpch_q08_market_share_ldmx"], "derived")
        self.assertEqual(classes["oy_th_real_supplier_right"], "industry")

    def test_final_row_wins_attempt_duplicate(self):
        attempts_path = "experiment_onoff_benchmark_20260818_120000.attempts.csv"
        final_path = "experiment_onoff_benchmark_20260818_120000.csv"
        sources = {
            attempts_path: result_frame([
                ("derived__ojb_job_21a_skeleton_ldmx", "job", 1.1, 1.2, "attempt"),
            ]),
            final_path: result_frame([
                ("derived__ojb_job_21a_skeleton_ldmx", "job", 2.1, 2.2, "final"),
            ]),
        }
        with mock.patch.object(PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()):
            loaded = PLOT.load([final_path, attempts_path])
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded.iloc[0]["marker"], "final")
        self.assertEqual(loaded.iloc[0]["query_class"], "derived")

    def test_new_shape_suffixes_are_recognized(self):
        cases = {
            "derived__ojb_job_21a_skeleton_ldmx": "left-deep",
            "derived__ojb_job_21a_skeleton_lduF": "left-deep",
            "derived__ojb_job_21a_skeleton_alt": "left-deep",
            "derived__ojb_job_21a_skeleton_rdmx": "right-deep",
            "derived__ojb_job_21a_skeleton_rdax": "right-deep",
            "derived__ojb_job_21a_skeleton_rduL": "right-deep",
            "derived__ojb_job_21a_skeleton_bmx": "bushy",
            "derived__ojb_job_21a_skeleton_bdmx": "bushy",
            "industry__oy_th_real_supplier_right": "industry",
        }
        self.assertEqual(
            {query: PLOT.topology_from_query(query) for query in cases}, cases
        )

    def test_old_win_prefixes_collapse_to_two_reporting_classes(self):
        self.assertEqual(PLOT.class_from_query("industrywin__old_query"), "industry")
        self.assertEqual(PLOT.class_from_query("legacywin__old_query"), "derived")


class PlotSpeedupPhaseTest(unittest.TestCase):
    @staticmethod
    def phase_row(query, family, total, baseline):
        return {
            "query": query,
            "display_query": f"[D] {query}",
            "family": family,
            "selected_plan": "OUTERYAN",
            "profile_round1_operator_s": 1.0,
            "profile_round2_operator_s": 2.0,
            "profile_round3_operator_s": 3.0,
            "profile_other_elapsed_s": 4.0,
            "profile_threads": 8,
            "profile_total_time_s": total,
            "profile_cpu_time_s": 10.0,
            "profile_round1_ratio": 0.1,
            "profile_round2_ratio": 0.2,
            "profile_round3_ratio": 0.3,
            "profile_other_ratio": 0.4,
            "tm_off": baseline,
            "t1_off": 99.0,
        }

    def test_all_families_share_one_phase_figure(self):
        frame = pd.DataFrame([
            self.phase_row("derived__ojb_tpch_q08_ldmx", "TPC-H", 2.0, 3.0),
            self.phase_row("derived__ojb_job_21a_rdmx", "JOB", 2.5, 4.0),
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_phase(object(), frame, "20260818_011114")

        self.assertEqual(len(captured), 1)
        labels = [label.get_text() for label in captured[0].axes[0].get_yticklabels()]
        self.assertTrue(any(label.startswith("TPC-H |") for label in labels))
        self.assertTrue(any(label.startswith("JOB |") for label in labels))
        legend = [text.get_text() for text in captured[0].axes[0].get_legend().get_texts()]
        self.assertIn(PLOT.OUTERYAN_TOTAL_LABEL, legend)
        self.assertIn(PLOT.BASELINE_LABEL, legend)
        self.assertEqual(captured[0].axes[0].get_xlabel(), "seconds")
        self.assertTrue(all(patch.get_hatch() is None for patch in captured[0].axes[0].patches))
        self.assertTrue(all(not patch.get_path_effects() for patch in captured[0].axes[0].patches))
        self.assertNotIn("20260818_011114", captured[0].axes[0].get_title())
        plt.close(captured[0])

    def test_phase_uses_matching_thread_baseline(self):
        frame = pd.DataFrame([
            self.phase_row("derived__ojb_tpch_q08_ldmx", "TPC-H", 2.0, 3.0),
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_phase(object(), frame, "20260818_011114")
        baseline_bar = captured[0].axes[0].patches[-1]
        endpoint = baseline_bar.get_x() + baseline_bar.get_width()
        self.assertTrue(math.isclose(endpoint, 3.0))
        plt.close(captured[0])


class PlotSpeedupBenchmarkPageTest(unittest.TestCase):
    def test_speedup_pages_are_separate_by_family(self):
        frame = pd.DataFrame([
            {
                "query": "derived__ojb_tpch_q08_ldmx",
                "display_query": "[D] derived__ojb_tpch_q08_ldmx",
                "family": "TPC-H",
                "selected_plan": "OUTERYAN",
                "t1_speedup": 1.1,
                "tm_speedup": 1.2,
            },
            {
                "query": "industry__oy_th_real_supplier_right",
                "display_query": "[I] industry__oy_th_real_supplier_right",
                "family": "TPC-H",
                "selected_plan": "DUCKDB",
                "t1_speedup": 0.9,
                "tm_speedup": 1.0,
            },
            {
                "query": "derived__ojb_job_21a_rdmx",
                "display_query": "[D] derived__ojb_job_21a_rdmx",
                "family": "JOB",
                "selected_plan": "OUTERYAN",
                "t1_speedup": 1.3,
                "tm_speedup": 1.4,
            },
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.pages_per_benchmark(object(), frame, "20260818_011114", "tm")

        self.assertEqual(len(captured), 2)
        titles = [figure.axes[0].get_title() for figure in captured]
        self.assertTrue(titles[0].startswith("TPC-H benchmark speed-up"))
        self.assertTrue(titles[1].startswith("JOB benchmark speed-up"))
        tpc_h_labels = [label.get_text() for label in captured[0].axes[0].get_yticklabels()]
        self.assertTrue(any(label.startswith("[D]") for label in tpc_h_labels))
        self.assertTrue(any(label.startswith("[I]") for label in tpc_h_labels))
        self.assertFalse(any("JOB" in label for label in tpc_h_labels))
        patches = [patch for figure in captured for patch in figure.axes[0].patches]
        self.assertTrue(all(patch.get_hatch() is None for patch in patches))
        self.assertTrue(all(not patch.get_path_effects() for patch in patches))
        self.assertTrue(all("20260818_011114" not in title for title in titles))
        for figure in captured:
            plt.close(figure)

    def test_summary_uses_short_titles_without_timestamp(self):
        frame = pd.DataFrame([
            {
                "query": "derived__ojb_tpch_q08_ldmx",
                "family": "TPC-H",
                "query_class": "derived",
                "reorder": 1,
                "t1_speedup": 1.1,
                "tm_speedup": 1.2,
            },
            {
                "query": "industry__oy_th_real_supplier_right",
                "family": "TPC-H",
                "query_class": "industry",
                "reorder": 0,
                "t1_speedup": 0.9,
                "tm_speedup": 1.0,
            },
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_summary(object(), frame, "20260818_011114")

        self.assertEqual([axis.get_title() for axis in captured[0].axes], [
            "Benchmark", "Query Category", "Join Order"
        ])
        self.assertEqual(captured[0]._suptitle.get_text(), "OuterYan benchmark speed-up summary")
        self.assertNotIn("20260818_011114", captured[0]._suptitle.get_text())
        plt.close(captured[0])


if __name__ == "__main__":
    unittest.main()
