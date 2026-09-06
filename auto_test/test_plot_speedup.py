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
        self.assertEqual(
            loaded.set_index("query").loc[
                "ojb_tpch_q08_market_share_ldmx", "display_query"
            ],
            "ojb_tpch_q08_market_share_ldmx",
        )

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

    def test_sql_relation_count_ignores_comments_and_overrides_stale_csv(self):
        frame = pd.DataFrame([{
            "query": "derived__sample_ldmx",
            "sql_path": "graph/derived__sample_ldmx.sql",
            "relation_count": 4,
        }])
        sql = "-- transformation: connected join-subgraph adaptation\nSELECT * FROM a JOIN b ON true JOIN c ON true"
        with mock.patch.object(Path, "read_text", return_value=sql):
            enriched = PLOT.enrich(frame, "20260830_002656")
        self.assertEqual(enriched.iloc[0]["relation_count"], 3)


class PlotSpeedupPhaseTest(unittest.TestCase):
    @staticmethod
    def phase_row(query, family, total, baseline):
        return {
            "query": query,
            "display_query": query,
            "family": family,
            "topology": PLOT.topology_from_query(query),
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
        self.assertEqual(len(captured[0].axes), 1)
        labels = [label.get_text() for label in captured[0].axes[0].get_xticklabels()]
        self.assertEqual(labels, ["H-LD-01", "J-RD-01"])
        subtitles = [text.get_text() for text in captured[0].axes[0].texts]
        self.assertIn("TPC-H (n=1)", subtitles)
        self.assertIn("JOB (n=1)", subtitles)
        legend = [text.get_text() for text in captured[0].legends[0].get_texts()]
        self.assertIn(PLOT.OUTERYAN_TOTAL_LABEL, legend)
        self.assertEqual(legend, [label for label, _, _, _ in PLOT.PHASES] + ["Total Time"])
        self.assertEqual(
            captured[0].axes[0].get_xlabel(), "Query"
        )
        patches = [patch for axis in captured[0].axes for patch in axis.patches]
        self.assertTrue(all(patch.get_hatch() is None for patch in patches))
        self.assertTrue(all(not patch.get_path_effects() for patch in patches))
        self.assertNotIn("20260818_011114", captured[0]._suptitle.get_text())
        plt.close(captured[0])

    def test_phase_omits_duckdb_baseline(self):
        frame = pd.DataFrame([
            self.phase_row("derived__ojb_tpch_q08_ldmx", "TPC-H", 2.0, 3.0),
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_phase(object(), frame, "20260818_011114")
        total_bar = captured[0].axes[0].patches[-1]
        endpoint = total_bar.get_y() + total_bar.get_height()
        self.assertTrue(math.isclose(endpoint, 2.0))
        legend = [text.get_text() for text in captured[0].legends[0].get_texts()]
        self.assertNotIn("DuckDB", " ".join(legend))
        plt.close(captured[0])

    def test_phase_sampling_caps_each_benchmark_at_twenty(self):
        rows = [
            self.phase_row(f"derived__ojb_job_{index:02d}_ldmx", "JOB", 2.0, 3.0)
            for index in range(25)
        ]
        sampled = PLOT.sample_phase_queries(PLOT.add_short_query_labels(pd.DataFrame(rows)))
        self.assertEqual(len(sampled), 20)
        self.assertTrue(sampled["_family_available"].eq(25).all())


class PlotSpeedupBenchmarkPageTest(unittest.TestCase):
    @staticmethod
    def runtime_row(query, family, plan, speedup, offset):
        return {
            "query": query,
            "display_query": query,
            "family": family,
            "topology": PLOT.topology_from_query(query),
            "selected_plan": plan,
            "t1_off": 10.0 + offset,
            "t1_on": (10.0 + offset) / speedup,
            "t1_speedup": speedup,
            "tm_off": 8.0 + offset,
            "tm_on": (8.0 + offset) / speedup,
            "tm_speedup": speedup,
        }

    def test_all_runtime_queries_share_one_dot_figure(self):
        frame = pd.DataFrame([
            self.runtime_row(
                "derived__ojb_tpch_q08_ldmx", "TPC-H", "OUTERYAN", 1.2, 0.0
            ),
            self.runtime_row(
                "industry__oy_th_real_supplier_right", "TPC-H", "DUCKDB", 1.0, 1.0
            ),
            self.runtime_row(
                "derived__ojb_job_21a_rdmx", "JOB", "OUTERYAN", 1.4, 2.0
            ),
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_runtime(object(), frame, "20260818_011114", "tm", selected_only=False)

        self.assertEqual(len(captured), 1)
        titles = [axis.get_title() for axis in captured[0].axes]
        self.assertTrue(any(title.startswith("TPC-H") for title in titles))
        self.assertTrue(any(title.startswith("JOB") for title in titles))
        labels = [
            label.get_text()
            for axis in captured[0].axes
            for label in axis.get_yticklabels()
        ]
        self.assertTrue(any(label.endswith("[OuterYan]") for label in labels))
        self.assertTrue(any(label.endswith("[DuckDB]") for label in labels))
        self.assertFalse(any(axis.patches for axis in captured[0].axes))
        self.assertTrue(all(len(axis.collections) == 2 for axis in captured[0].axes))
        self.assertEqual(captured[0]._suptitle.get_text(), "Runtime - all correct and timed queries")
        plt.close(captured[0])

    def test_outeryan_runtime_splits_job_and_preserves_both_timing_pairs(self):
        frame = pd.DataFrame([
            self.runtime_row("derived__selected", "TPC-H", "OUTERYAN", 1.2, 0.0),
            self.runtime_row("derived__not_selected", "TPC-H", "DUCKDB", 1.0, 1.0),
            self.runtime_row("derived__job_selected", "JOB", "OUTERYAN", 2.0, 4.0),
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_runtime(object(), frame, "20260818_011114", "tm", selected_only=True)
        self.assertEqual(len(captured), 2)
        for figure, label, expected in zip(
            captured, ["H-O-01", "J-O-01"],
            [[10.0, 10.0 / 1.2, 8.0, 8.0 / 1.2], [14.0, 7.0, 12.0, 6.0]],
        ):
            axis = figure.axes[0]
            self.assertEqual([text.get_text() for text in axis.get_xticklabels()], [label])
            self.assertEqual(len(axis.patches), 4)
            for bar, seconds in zip(axis.patches, expected):
                self.assertAlmostEqual(bar.get_y() + bar.get_height(), seconds)
            self.assertFalse(axis.collections)
            self.assertEqual(figure._suptitle.get_text(), "Running time Comparison")
            plt.close(figure)

    def test_selected_runtime_requires_all_four_valid_timings(self):
        valid = self.runtime_row("derived__valid", "TPC-H", "OUTERYAN", 1.2, 0.0)
        for _, column, _ in PLOT.RUNTIME_SERIES:
            for value in [float("nan"), float("inf"), -float("inf"), None, "missing", 0, -1]:
                with self.subTest(column=column, value=value):
                    incomplete = dict(valid, query="derived__incomplete")
                    incomplete[column] = value
                    measured = PLOT.selected_runtime_rows(pd.DataFrame([valid, incomplete]))
                    self.assertEqual(measured["query"].tolist(), ["derived__valid"])
            with self.subTest(column=column, absent=True):
                frame = pd.DataFrame([valid]).drop(columns=[column])
                self.assertTrue(PLOT.selected_runtime_rows(frame).empty)

    def test_selected_runtime_omits_incomplete_queries_without_renumbering(self):
        incomplete = self.runtime_row("derived__a_missing", "TPC-H", "OUTERYAN", 1.2, 0.0)
        incomplete["t1_on"] = float("nan")
        valid = self.runtime_row("derived__b_valid", "TPC-H", "OUTERYAN", 1.2, 0.0)
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_runtime(
                object(), pd.DataFrame([incomplete, valid]), "test", "tm", selected_only=True
            )
        self.assertEqual(len(captured), 1)
        axis = captured[0].axes[0]
        self.assertEqual([text.get_text() for text in axis.get_xticklabels()], ["H-O-02"])
        self.assertEqual(len(axis.patches), 4)
        self.assertFalse(axis.collections)
        legend = [text.get_text() for text in captured[0].legends[0].get_texts()]
        self.assertEqual(legend, [label for label, _, _ in PLOT.RUNTIME_SERIES])
        plt.close(captured[0])

    def test_selected_runtime_omits_figure_when_all_queries_are_incomplete(self):
        row = self.runtime_row("derived__incomplete", "TPC-H", "OUTERYAN", 1.2, 0.0)
        row["tm_on"] = float("nan")
        with mock.patch.object(PLOT, "save_page") as save:
            PLOT.page_runtime(object(), pd.DataFrame([row]), "test", "tm", selected_only=True)
        save.assert_not_called()

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
