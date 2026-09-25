#!/usr/bin/env python3

import importlib.util
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import matplotlib.pyplot as plt
import pandas as pd


PLOT_PATH = Path(__file__).with_name("plot_speedup.py")
SPEC = importlib.util.spec_from_file_location("plot_speedup", PLOT_PATH)
PLOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLOT)


def empty_benchmark_provenance():
    return pd.DataFrame(columns=[
        "query_id", "source_component", "evaluation_role", "workload_component",
    ])


def result_frame(rows):
    return pd.DataFrame(
        rows,
        columns=["query", "family", "t1_speedup", "tm_speedup", "marker"],
    )


class PlotSpeedupLoadTest(unittest.TestCase):
    def test_thread_sweeps_are_distinct_runs(self):
        for threads in (16, 32):
            for attempts in (False, True):
                suffix = ".attempts" if attempts else ""
                self.assertEqual(
                    PLOT.result_source(f"experiment_onoff_benchmark_20260908_120000_t{threads}{suffix}.csv"),
                    (f"20260908_120000_t{threads}", "attempts" if attempts else "final", "benchmark"),
                )

    def test_multi_thread_only_runs_do_not_require_single_thread_columns(self):
        sources = {
            f"experiment_onoff_benchmark_20260908_120000_t{threads}.csv": pd.DataFrame([{
                "query": "derived__sample", "family": "tpch", "correct": "TRUE",
                "timing_threads": threads, "tm_off": 10.0, "tm_on": 5.0, "tm_speedup": 2.0,
            }]) for threads in (16, 32)
        }
        with mock.patch.object(
            PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()
        ), mock.patch.object(
            PLOT, "benchmark_provenance", side_effect=empty_benchmark_provenance
        ):
            loaded = PLOT.timed(PLOT.load(list(sources)))
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded["run"].nunique(), 2)
        self.assertEqual(set(loaded["timing_threads"]), {16, 32})
        self.assertNotIn("t1_off", loaded)

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
        with mock.patch.object(
            PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()
        ), mock.patch.object(
            PLOT, "benchmark_provenance", side_effect=empty_benchmark_provenance
        ):
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
        with mock.patch.object(
            PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()
        ), mock.patch.object(
            PLOT, "benchmark_provenance", side_effect=empty_benchmark_provenance
        ):
            loaded = PLOT.load([final_path, attempts_path])
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded.iloc[0]["marker"], "final")
        self.assertEqual(loaded.iloc[0]["query_class"], "derived")

    def test_combined_versions_share_experiment_group_without_cross_version_dedup(self):
        paths = ["result_v1.csv", "result_v2.csv", "result_all.csv"]
        common = {
            "query": "derived__same", "family": "tpch", "correct": "TRUE",
            "timing_threads": 32, "tm_off": 2.0, "tm_on": 1.0, "tm_speedup": 2.0,
            "experiment_group": "20260925_120000",
        }
        sources = {
            paths[0]: pd.DataFrame([dict(common, workload_category="v1")]),
            paths[1]: pd.DataFrame([dict(common, workload_category="v2")]),
            paths[2]: pd.DataFrame([
                dict(common, workload_category="v1"),
                dict(common, workload_category="v2"),
            ]),
        }
        with mock.patch.object(
            PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()
        ), mock.patch.object(
            PLOT, "benchmark_provenance", side_effect=empty_benchmark_provenance
        ):
            loaded = PLOT.load(paths)
        self.assertEqual(loaded["run"].unique().tolist(), ["20260925_120000"])
        self.assertEqual(len(loaded), 2)
        self.assertEqual(set(loaded["workload_category"]), {"v1", "v2"})

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
            "stress__ojb_job_30a_skeleton_rduR_stress0025": "right-deep",
            "stress__ojb_job_30a_skeleton_rduR_stress80": "right-deep",
            "regression__ojb_sqlstorm_job_11914_bdmx": "bushy",
        }
        self.assertEqual(
            {query: PLOT.topology_from_query(query) for query in cases}, cases
        )

    def test_old_win_prefixes_collapse_to_two_reporting_classes(self):
        self.assertEqual(PLOT.class_from_query("industrywin__old_query"), "industry")
        self.assertEqual(PLOT.class_from_query("legacywin__old_query"), "derived")
        self.assertEqual(
            PLOT.class_from_query("stress__ojb_job_30a_skeleton_rduR_stress0025"),
            "selectivity stress",
        )
        self.assertEqual(
            PLOT.class_from_query("regression__ojb_sqlstorm_job_11914_bdmx"),
            "JOB regression",
        )

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
            "tm_on": baseline / 2.0,
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
        self.assertEqual(len(captured[0].axes), 2)
        axis, runtime_axis = captured[0].axes
        labels = [label.get_text() for label in axis.get_yticklabels()]
        self.assertEqual(labels, ["H-LD-01", "J-RD-01"])
        benchmark_labels = [text for text in axis.texts if text.get_text() in {"TPC-H", "JOB"}]
        self.assertEqual([text.get_text() for text in benchmark_labels], ["TPC-H", "JOB"])
        self.assertTrue(all(text.get_rotation() == 90 for text in benchmark_labels))
        self.assertTrue(all(text.get_position()[0] == -0.074 for text in benchmark_labels))
        self.assertEqual(len(axis.lines), 1)
        legend = [text.get_text() for text in axis.get_legend().get_texts()]
        self.assertEqual(legend, [label for label, _, _, _ in PLOT.PHASES])
        self.assertEqual(axis.get_xlabel(), "CPU Time (%)")
        self.assertEqual(runtime_axis.get_xscale(), "log")
        self.assertEqual(runtime_axis.get_xlabel(), "Running time: DuckDB vs. OuterYan")
        self.assertTrue(runtime_axis.get_axisbelow())
        self.assertTrue(all(line.get_zorder() == 0 for line in runtime_axis.get_xgridlines()))
        self.assertEqual(
            [text.get_text() for text in runtime_axis.get_legend().get_texts()],
            ["DuckDB", "OuterYan"],
        )
        phase_colors = {color.lower() for _, _, _, color in PLOT.PHASES}
        self.assertNotIn(PLOT.PHASE_RUNTIME_DUCKDB_COLOR.lower(), phase_colors)
        self.assertNotIn(PLOT.PHASE_RUNTIME_OUTERYAN_COLOR.lower(), phase_colors)
        self.assertNotEqual(
            PLOT.PHASE_RUNTIME_DUCKDB_COLOR.lower(),
            PLOT.PHASE_RUNTIME_OUTERYAN_COLOR.lower(),
        )
        runtime_points = [
            collection.get_offsets().tolist() for collection in runtime_axis.collections
            if collection.__class__.__name__ == "PathCollection"
        ]
        expected_y = 1.0 + PLOT.PHASE_GROUP_GAP
        self.assertEqual(
            runtime_points,
            [[[3.0, 0.0], [4.0, expected_y]], [[1.5, 0.0], [2.0, expected_y]]],
        )
        self.assertGreater(expected_y, 1.0)
        self.assertEqual(
            [collection.get_sizes().tolist() for collection in runtime_axis.collections],
            [[38], [42]],
        )
        self.assertEqual(
            [text.get_text() for text in runtime_axis.texts],
            ["2.00×", "2.00×"],
        )
        self.assertTrue(all(text.get_position()[0] == 1.040 for text in runtime_axis.texts))
        patches = axis.patches
        self.assertTrue(all(patch.get_hatch() is None for patch in patches))
        self.assertTrue(all(not patch.get_path_effects() for patch in patches))
        self.assertIsNone(captured[0]._suptitle)
        plt.close(captured[0])

    def test_v2_selectivity_suffix_preserves_tree_shape_label(self):
        self.assertEqual(
            PLOT.topology_from_query("derived__ojb_tpch_q08_ldmx_sel001"),
            "left-deep",
        )
        self.assertEqual(
            PLOT.topology_from_query("derived__ojb_job_21a_rduR_sel01"),
            "right-deep",
        )
        self.assertEqual(
            PLOT.topology_from_query("derived__ojb_tpcds_q72_bdmx_sel05"),
            "bushy",
        )

    def test_phase_uses_cpu_total_and_component_closure(self):
        frame = pd.DataFrame([
            self.phase_row("derived__ojb_tpch_q08_ldmx", "TPC-H", 2.0, 3.0),
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_phase(object(), frame, "20260818_011114")
        axis = captured[0].axes[0]
        self.assertAlmostEqual(sum(patch.get_width() for patch in axis.patches), 100.0)
        self.assertIn("10.0 s", [text.get_text() for text in axis.texts])
        complete, skipped = PLOT.complete_phase_rows(frame)
        self.assertEqual(skipped, 0)
        self.assertAlmostEqual(complete.iloc[0]["_phase_sum_s"], 10.0)
        self.assertAlmostEqual(complete.iloc[0]["_phase_sum_error_s"], 0.0)
        plt.close(captured[0])

    def test_phase_baseline_never_uses_a_mismatched_thread_count(self):
        legacy = self.phase_row("q", "JOB", 2, 3)
        for row, expected in (
            (legacy, 3), (dict(legacy, timing_threads=8), 3),
            (dict(legacy, timing_threads=32), None), (dict(legacy, tm_off=math.nan), None),
            (dict(legacy, profile_threads=1), 99),
        ):
            rows = PLOT.phase_baseline_rows(pd.DataFrame([row]))
            if expected is None:
                self.assertTrue(rows.empty)
            else:
                self.assertEqual(rows.iloc[0]["baseline_time_s"], expected)

    def test_runtime_and_phase_use_one_sample_and_short_name_mapping(self):
        current = pd.DataFrame([
            dict(self.phase_row(f"q{i}", "JOB", 2, 30 + i), timing_threads=32,
                 tm_on=40 + i, selected_plan="DUCKDB" if i == 0 else "OUTERYAN")
            for i in range(5)
        ]).drop(columns=[column for column in self.phase_row("q", "JOB", 2, 3) if column.startswith("profile_")])
        legacy = pd.DataFrame([dict(self.phase_row(f"q{i}", "JOB", 2, 3 + i), profile_threads=48)
                               for i in (0, 1, 2, 3)])
        sample, phases = PLOT.paired_representative_samples(current, legacy, limit=15)
        self.assertEqual(sample["query"].tolist(), ["q1", "q2", "q3"])
        self.assertEqual(sample["query"].tolist(), phases["query"].tolist())
        self.assertEqual(sample["short_query"].tolist(), phases["short_query"].tolist())
        self.assertEqual(set(sample["selected_plan"]), {"OUTERYAN"})
        self.assertTrue((sample.tm_off / sample.tm_on).lt(1).all())  # Regressions stay eligible.
        self.assertEqual(phases["baseline_time_s"].tolist(), [4, 5, 6])
        self.assertEqual(sample["tm_off"].tolist(), [31, 32, 33])
        self.assertEqual(phases["baseline_threads"].tolist(), [48, 48, 48])

    def test_profiles_not_available_does_not_prevent_runtime_sampling(self):
        row = dict(self.phase_row("q", "JOB", 2, 3), timing_threads=32, tm_on=4)
        frame = pd.DataFrame([row]).drop(columns=[column for column in row if column.startswith("profile_")])
        sample, phases = PLOT.paired_representative_samples(frame, frame)
        self.assertEqual(sample["query"].tolist(), ["q"])
        self.assertTrue(phases.empty)

    def test_legacy_phase_placeholder_is_separate_and_visibly_labeled(self):
        current = pd.DataFrame([{"run": "20260908_235240_t32", "timing_threads": 32}])
        legacy = pd.DataFrame([dict(
            self.phase_row("derived__ojb_tpch_q08_ldmx", "TPC-H", 2.0, 3.0),
            run="20260830_002656", profile_threads=48,
        )])
        frame, notice = PLOT.phase_source(current, legacy)
        self.assertIs(frame, legacy)
        self.assertIn("2026-08-30", notice)
        self.assertIn("48 threads", notice)
        self.assertIn("not current 32-thread results", notice)
        self.assertEqual(list(current.columns), ["run", "timing_threads"])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_phase(object(), frame, "current", notice)
        self.assertIn(notice, [text.get_text() for text in captured[0].texts])
        plt.close(captured[0])

    def test_current_profiles_replace_legacy_placeholder(self):
        current = pd.DataFrame([self.phase_row("derived__ojb_tpch_q08_ldmx", "TPC-H", 2.0, 3.0)])
        frame, notice = PLOT.phase_source(current, pd.DataFrame())
        self.assertIs(frame, current)
        self.assertIsNone(notice)

    def test_phase_placeholder_requires_complete_profiles_with_known_threads(self):
        current = pd.DataFrame([{"timing_threads": 32}])
        for legacy in (
            pd.DataFrame(),
            pd.DataFrame([dict(self.phase_row("q", "JOB", 2.0, 3.0), run="old", profile_threads=math.nan)]),
            pd.DataFrame([dict(self.phase_row("q", "JOB", 2.0, 3.0), run="old", profile_threads=0)]),
        ):
            with self.assertRaises(ValueError):
                PLOT.phase_source(current, legacy)

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

    def test_all_queries_use_compact_runtime_pair_without_query_names(self):
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
            PLOT.page_speedup_scatter(object(), frame, "20260818_011114", "tm")

        self.assertEqual(len(captured), 1)
        self.assertEqual(len(captured[0].axes), 2)
        family_axis, distribution_axis = captured[0].axes
        points = [
            point
            for collection in family_axis.collections
            if collection.__class__.__name__ == "PathCollection"
            for point in collection.get_offsets().tolist()
        ]
        self.assertEqual(sorted(points), sorted([[8.0, 8.0 / 1.2], [9.0, 9.0], [10.0, 10.0 / 1.4]]))
        self.assertEqual(family_axis.get_xscale(), "log")
        self.assertEqual(family_axis.get_yscale(), "log")
        self.assertEqual([text.get_text() for text in distribution_axis.get_yticklabels()], ["TPC-H", "JOB"])
        labels = [
            text.get_text()
            for axis in captured[0].axes
            for text in axis.texts + axis.get_xticklabels() + axis.get_yticklabels()
        ]
        self.assertFalse(any(query in " ".join(labels) for query in frame["query"]))
        self.assertIsNone(family_axis.get_legend())
        self.assertIsNone(distribution_axis.get_legend())
        self.assertEqual(len(captured[0].legends), 1)
        figure_legend = captured[0].legends[0]
        self.assertEqual(figure_legend.get_title().get_text(), "")
        all_text = [text.get_text() for text in figure_legend.get_texts()]
        self.assertEqual(
            all_text,
            ["TPC-H", "JOB", "OuterYan faster/equal", "OuterYan slower"],
        )
        self.assertFalse(any("(n=" in text for text in all_text))
        self.assertIsNone(captured[0]._suptitle)
        self.assertLess(
            distribution_axis.get_position().x0 - family_axis.get_position().x1, 0.08
        )
        panel_labels = [text for axis in captured[0].axes for text in axis.texts if text.get_text().startswith("(")]
        self.assertTrue(all(text.get_position()[1] > -0.15 for text in panel_labels))
        self.assertEqual(
            [text.get_text() for text in panel_labels],
            ["(a) Running Time Comparison", "(b) Speed-up Comparison"],
        )
        self.assertEqual(distribution_axis.get_xlabel(), "DuckDB vs. OuterYan")
        scatter = [
            collection for collection in family_axis.collections
            if collection.__class__.__name__ == "PathCollection" and len(collection.get_offsets())
        ]
        self.assertNotEqual(scatter[0].get_facecolors().tolist(), scatter[-1].get_facecolors().tolist())
        self.assertTrue(all(collection.get_sizes().tolist() == [PLOT.QUERY_POINT_SIZE]
                            for collection in scatter))
        self.assertTrue(all(collection.get_alpha() == PLOT.QUERY_POINT_ALPHA
                            for collection in scatter))
        distribution_points = [
            collection for collection in distribution_axis.collections
            if collection.__class__.__name__ == "PathCollection"
            and collection.get_alpha() == PLOT.QUERY_POINT_ALPHA
        ]
        self.assertEqual(len(distribution_points), 2)
        self.assertTrue(all(collection.get_sizes().tolist() == [PLOT.QUERY_POINT_SIZE]
                            for collection in distribution_points))
        plt.close(captured[0])

    def test_representatives_balance_families_and_cover_shapes_deterministically(self):
        rows = []
        for family, count in zip(PLOT.FAMILY_ORDER, [5, 8, 12, 38]):
            for index in range(count):
                suffix = ["ldmx", "rdmx", "bmx"][index % 3]
                rows.append(self.runtime_row(f"derived__{family}_{index:02d}_{suffix}", family,
                                             "OUTERYAN", 0.8 if index % 2 else 2.0, float(index)))
        frame = pd.DataFrame(rows)
        sample = PLOT.representative_runtime_rows(frame)
        self.assertEqual(sample.groupby("family").size().to_dict(), dict(zip(PLOT.FAMILY_ORDER, [5, 8, 12, 15])))
        self.assertEqual(len(sample["query"].unique()), 40)
        for family in PLOT.FAMILY_ORDER:
            self.assertEqual(set(sample.loc[sample["family"].eq(family), "topology"]),
                             {"left-deep", "right-deep", "bushy"})
        shuffled = PLOT.representative_runtime_rows(frame.sample(frac=1, random_state=27))
        self.assertEqual(sample["query"].tolist(), shuffled["query"].tolist())
        # Selection must not depend on ON timing or speed-up ranking.
        changed = frame.assign(t1_on=0.25, tm_on=0.5, t1_speedup=99.0, tm_speedup=99.0)
        self.assertEqual(sample["query"].tolist(), PLOT.representative_runtime_rows(changed)["query"].tolist())

    def test_sample_quota_uses_complete_eligible_rows_only(self):
        rows = [self.runtime_row(f"derived__{family}_{i}_ldmx", family, "OUTERYAN", 1.2, float(i))
                for family in ("TPC-H", "JOB") for i in range(6)]
        frame = pd.DataFrame(rows)
        frame.loc[0, "tm_on"] = float("nan")
        frame.loc[1, "selected_plan"] = "DUCKDB"
        frame.loc[2, "correct"] = "FALSE"
        frame["correct"] = frame["correct"].fillna("TRUE")
        sample = PLOT.representative_runtime_rows(frame)
        self.assertEqual(sample.groupby("family").size().to_dict(), {"TPC-H": 3, "JOB": 6})
        self.assertTrue(set(frame.loc[:2, "query"]).isdisjoint(sample["query"]))
        with self.assertRaises(ValueError):
            PLOT.representative_runtime_rows(frame, 0)

    def test_all_plan_sample_targets_fifteen_and_is_plan_independent(self):
        rows = []
        for family, count in zip(PLOT.FAMILY_ORDER, [5, 48, 41, 82]):
            for index in range(count):
                suffix = ["ldmx", "rdmx", "bmx"][index % 3]
                row = self.runtime_row(f"derived__{family}_{index:03d}_{suffix}", family,
                                       "OUTERYAN" if index % 4 == 0 else "DUCKDB", 1.2, index)
                rows.append(row)
        frame = pd.DataFrame(rows)
        sample = PLOT.representative_runtime_rows(frame, scope="all")
        self.assertEqual(sample.groupby("family").size().to_dict(), dict(zip(PLOT.FAMILY_ORDER, [5, 15, 15, 15])))
        self.assertEqual(len(sample["query"].unique()), 50)
        self.assertEqual(set(sample["selected_plan"]), {"OUTERYAN", "DUCKDB"})
        for family in PLOT.FAMILY_ORDER:
            self.assertEqual(set(sample.loc[sample["family"].eq(family), "topology"]),
                             {"left-deep", "right-deep", "bushy"})
        changed = frame.assign(selected_plan="DUCKDB", t1_on=0.3, tm_on=0.5)
        shuffled = changed.sample(frac=1, random_state=43)
        self.assertEqual(sample["query"].tolist(),
                         PLOT.representative_runtime_rows(shuffled, scope="all")["query"].tolist())
        with self.assertRaises(ValueError):
            PLOT.representative_runtime_rows(frame, scope="invalid")

    def test_all_plan_sample_excludes_failed_missing_and_timeout_records(self):
        good = self.runtime_row("derived__good", "TPC-H", "DUCKDB", 1.0, 0)
        frame = pd.DataFrame([
            good, dict(good, query="derived__missing", tm_on=None),
            dict(good, query="derived__failed", correct=False),
            dict(good, query="derived__timeout", note="ON_TIMEOUT"),
        ])
        frame["correct"] = frame["correct"].astype("boolean").fillna(True)
        sample = PLOT.representative_runtime_rows(frame, scope="all")
        self.assertEqual(sample["query"].tolist(), ["derived__good"])

    def test_speedup_scatter_rejects_failed_and_missing_data(self):
        good = self.runtime_row("derived__good", "TPC-H", "OUTERYAN", 2.0, 0.0)
        rows = [good, dict(good, query="missing", tm_on=float("nan")),
                dict(good, query="zero", tm_off=0), dict(good, query="failed", correct="FALSE")]
        frame = pd.DataFrame(rows)
        frame["correct"] = frame["correct"].fillna("TRUE")
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_speedup_scatter(object(), frame, "test", "tm")
        points = captured[0].axes[0].collections[0].get_offsets().tolist()
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0], [8.0, 4.0])
        plt.close(captured[0])

    def test_fallback_skip_is_kept_for_speedup_distribution_only(self):
        measured = self.runtime_row("derived__measured", "TPC-H", "OUTERYAN", 2.0, 0.0)
        fallback = dict(
            measured,
            query="derived__fallback",
            selected_plan="DUCKDB",
            correct="SKIPPED",
            note="FALLBACK-SKIP",
            timing_status="fallback-skip",
            tm_off=float("nan"),
            tm_on=float("nan"),
            tm_speedup=1.0,
        )
        frame = pd.DataFrame([measured, fallback])
        self.assertEqual(PLOT.timed(frame)["query"].tolist(), ["derived__measured", "derived__fallback"])
        self.assertEqual(PLOT.complete_runtime_rows(frame)["query"].tolist(), ["derived__measured"])

    def test_runtime_scatter_order_is_stable(self):
        frame = pd.DataFrame([
            self.runtime_row(f"derived__{index}_{suffix}", family, "OUTERYAN", 1 + index / 10, 0)
            for index, (family, suffix) in enumerate([
                ("TPC-H", "ldmx"), ("TPC-H", "rdmx"), ("TPC-H", "bmx"),
                ("TPC-H", "ldmx"), ("JOB", "ldmx"), ("JOB", "rdmx")])
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_speedup_scatter(object(), frame, "test", "tm")
            PLOT.page_speedup_scatter(object(), frame.sample(frac=1, random_state=8), "test", "tm")
        points = [
            collection.get_offsets().tolist() for collection in captured[0].axes[0].collections
            if collection.__class__.__name__ == "PathCollection"
        ]
        self.assertEqual(captured[0].axes[0].get_xlabel(), "DuckDB running time (s)")
        self.assertEqual(points, [
            collection.get_offsets().tolist() for collection in captured[1].axes[0].collections
            if collection.__class__.__name__ == "PathCollection"
        ])
        self.assertEqual([point[0] for point in points[0]], [8.0, 8.0, 8.0, 8.0])
        for figure in captured:
            plt.close(figure)

    def test_standalone_outputs_merge_benchmarks_and_skip_absent_profiles(self):
        frame = pd.DataFrame([
            self.runtime_row("derived__h_ldmx", "TPC-H", "OUTERYAN", 1.1, 0.0),
            self.runtime_row("derived__j_bmx", "JOB", "OUTERYAN", 1.2, 0.0),
        ])
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(PLOT, "PdfPages"), \
                mock.patch.object(PLOT, "page_speedup_scatter"):
            output_directory = Path(directory)
            obsolete = [
                "runtime_outeryan_queries.pdf", "runtime_outeryan_queries.png",
                "runtime_representative_queries.pdf", "runtime_representative_queries.png",
                "representative_queries.json",
            ]
            for filename in obsolete:
                (output_directory / filename).write_text("obsolete")
            paths = PLOT.write_standalone_runtime_figures(Path(directory), frame, "test", "tm")
            self.assertEqual([path.name for path in paths], ["speedup_all_queries.pdf"])
            self.assertTrue(all(not (output_directory / filename).exists() for filename in obsolete))

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
