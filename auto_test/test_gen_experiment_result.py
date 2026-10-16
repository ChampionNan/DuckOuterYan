"""Regression tests for unified result loading, statistics, figures and paper tables."""

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from auto_test import gen_experiment_result as RESULT

RESULT._load_plotting()
pd, plt = RESULT.pd, RESULT.plt
STATS = PLOT = PAPER = RESULT


class BenchmarkStatisticsTest(unittest.TestCase):
    def test_independent_timeouts_preserve_completed_side_but_exclude_pairs(self):
        frame = self.frame()
        frame["correct"] = frame["correct"].astype(str)
        frame["timeout_seconds"] = "NA"
        frame["duckdb_timeout_seconds"] = 600
        frame["outeryan_timeout_seconds"] = 300
        frame["duckdb_status"] = ["timeout", "measured", "measured"]
        frame["outeryan_status"] = ["measured", "timeout", "measured"]
        frame["duckdb_timeout_stage"] = ["correctness", "-", "-"]
        frame["outeryan_timeout_stage"] = ["-", "timing", "-"]
        frame.loc[0, ["correct", "note", "tm_off"]] = ["TIMEOUT", "TIMEOUT-OFF-CORRECTNESS", float("nan")]
        frame.loc[1, ["note", "tm_on"]] = ["TIMEOUT-ON-TIMING", float("nan")]
        detail = RESULT.prepare_queries(frame, "tm")
        self.assertEqual(detail["valid_timing"].tolist(), [False, False, True])
        report = RESULT.build_timeout_statistics(detail)
        self.assertIsNone(report["limit_seconds"])
        self.assertEqual(report["recorded_limits_seconds"], [300, 600])
        self.assertEqual(report["per_engine"]["duckdb"]["timeout_queries"], 1)
        self.assertEqual(report["per_engine"]["outeryan"]["timeout_queries"], 1)
        self.assertEqual(report["per_engine"]["duckdb"]["stages"], {"correctness": 1})
        self.assertEqual(report["queries"][0]["on_s"], 2)
        self.assertIsNone(report["queries"][0]["off_s"])

    def test_timeout_uses_recorded_limit_without_relabeling_legacy_data(self):
        frame = self.frame()
        for timeout in (900, 1800):
            frame["timeout_seconds"] = timeout
            detail = RESULT.prepare_queries(frame, "tm")
            self.assertEqual(RESULT.build_timeout_statistics(detail)["limit_seconds"], timeout)
        self.assertEqual(RESULT.build_timeout_statistics(detail.drop(columns="timeout_seconds"))["limit_seconds"], 600)

    def test_curated_population_is_explicitly_disclosed(self):
        frame = self.frame()
        frame["qualification_policy"] = "performance_screened"
        report = RESULT.build_statistics(frame)
        self.assertIn("not an unbiased", report["method"]["population"])
        self.assertIn("recorded timeout", report["method"]["population"])
        self.assertNotIn("1800s", report["method"]["population"])

    def test_generated_file_cleanup_supports_python37_and_preserves_errors(self):
        original_unlink = Path.unlink

        # Python 3.7 accepts no missing_ok argument, even on newer test runtimes.
        def unlink_python37(path):
            return original_unlink(path)

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(Path, "unlink", unlink_python37):
            root = Path(directory)
            output = root / "obsolete.tex"
            output.write_text("obsolete output")
            RESULT.remove_generated_file(output)
            self.assertFalse(output.exists())
            RESULT.remove_generated_file(output)
            with self.assertRaises(OSError):
                RESULT.remove_generated_file(root)

    @staticmethod
    def frame():
        return pd.DataFrame([
            {"query": name, "family": family, "topology": shape, "selected_plan": plan,
             "correct": True, "note": "OK", "tm_off": off, "tm_on": 2,
             "tm_speedup": 99, "run": "20260908_235240_t32", "timing_threads": 32}
            for name, family, shape, plan, off in [
                ("slow", "TPC-H", "left-deep", "OUTERYAN", 1),
                ("equal", "TPC-H", "right-deep", "DUCKDB", 2),
                ("fast", "JOB", "bushy", "OUTERYAN", 4),
            ]
        ])

    def test_exact_pair_statistics_not_rounded_speedup_or_sample(self):
        report = STATS.build_statistics(self.frame())
        summary = report["groups"][0]
        self.assertEqual(summary["counts"]["valid"], 3)
        self.assertEqual(summary["speedup"]["min"], 0.5)
        self.assertEqual(summary["speedup"]["max"], 2)
        self.assertEqual(summary["speedup"]["geomean"], 1)
        self.assertAlmostEqual(summary["speedup"]["mean"], 7 / 6)
        self.assertEqual(summary["speedup"]["median"], 1)
        self.assertAlmostEqual(summary["speedup"]["stddev"], math.sqrt(7 / 12))
        self.assertAlmostEqual(summary["speedup"]["p95"], 1.9)
        self.assertEqual(summary["speedup"]["min_queries"], ["slow"])
        self.assertEqual(summary["speedup"]["max_queries"], ["fast"])
        self.assertEqual(summary["totals"]["off_s"], 7)
        self.assertEqual(summary["totals"]["on_s"], 6)
        self.assertAlmostEqual(summary["totals"]["speedup"], 7 / 6)
        self.assertEqual([summary["counts"][key] for key in ("faster", "equal", "slower")], [1, 1, 1])
        self.assertEqual(summary["off_s"]["max"], 4)

    def test_unchecked_requires_explicit_opt_out_and_executed_timing(self):
        frame = self.frame()
        frame["correct"] = "NOT-CHECKED"
        frame["correctness_check"] = "disabled"
        frame["timing_status"] = "measured"
        frame["timing_samples"] = 1
        frame["timing_estimator"] = "single_post_warmup"
        report = STATS.build_statistics(frame)
        self.assertEqual(report["groups"][0]["counts"]["measured"], 3)
        self.assertEqual(report["groups"][0]["counts"]["unchecked_measured"], 3)
        self.assertEqual(report["method"]["timing_protocols"][0]["timing_samples"], 1)
        self.assertTrue(all(r["correct"] == "NOT-CHECKED" for r in report["queries"]))
        for column in ("correctness_check", "timing_status"):
            self.assertEqual(STATS.build_statistics(frame.drop(columns=column))["valid_queries"], 0)
        frame["correct"] = "FALSE"
        self.assertEqual(STATS.build_statistics(frame)["valid_queries"], 0)

    def test_minimum_runtime_filter_is_symmetric_strict_and_keeps_coverage(self):
        base = self.frame().iloc[0].to_dict()
        frame = pd.DataFrame([
            dict(base, query=name, tm_off=off, tm_on=on)
            for name, off, on in (
                ("short_win", 0.8, 0.2), ("short_loss", 0.2, 0.8),
                ("just_below", 0.999999999, 0.999999999),
                ("off_boundary", 1.0, 0.1), ("on_boundary", 0.1, 1.0),
                ("large_win", 10.0, 0.01), ("large_loss", 0.01, 10.0),
                ("missing", None, 0.1), ("invalid", 0, 0.1),
            )
        ], index=[9, 3, 27, 14, 2, 18, 5, 40, 11])
        report = STATS.build_statistics(frame)
        counts = report["groups"][0]["counts"]
        self.assertEqual(report["unique_queries"], 9)
        self.assertEqual(counts["measured"], 4)
        self.assertEqual(counts["both_runtimes_below_1s"], 3)
        self.assertEqual(counts["missing_or_invalid_timing"], 2)
        detail = {row["query"]: row for row in report["queries"]}
        self.assertEqual(detail["short_loss"]["off_s"], 0.2)
        self.assertEqual(detail["short_loss"]["exclusion_reason"], "both_runtimes_below_1s")
        self.assertIsNone(detail["short_loss"]["speedup"])
        self.assertTrue(detail["large_loss"]["valid_timing"])
        self.assertIn("Both <1s excluded", STATS.markdown_report(report))
        frame["t1_off"], frame["t1_on"] = 2.0, 3.0
        self.assertFalse(STATS.below_runtime_threshold(frame, "t1").any())

    def test_phase_and_optimizer_summaries_use_query_runtime_threshold(self):
        base = self.frame().iloc[0].to_dict()
        frame = pd.DataFrame([
            dict(base, query="short", tm_off=0.2, tm_on=0.4),
            dict(base, query="kept", tm_off=1.0, tm_on=0.4),
        ])
        frame["profile_status"] = frame["optimizer_profile_status"] = "OK"
        frame["profile_threads"] = 32
        frame["profile_wall_time_s"] = 0.4
        frame["profile_cpu_time_s"] = 10.0
        for (_, column), seconds in zip(STATS.PHASE_COMPONENTS, (1, 2, 3, 4)):
            frame[column] = seconds
        frame["optimizer_duckdb_total_s"] = 0.001
        frame["optimizer_outeryan_total_s"] = 0.002
        frame["optimizer_duckdb_phases_json"] = '{"other":0.001}'
        frame["optimizer_outeryan_phases_json"] = '{"other":0.002}'
        report = STATS.build_statistics(frame)
        for key in ("phase_profiles", "optimizer_profiles"):
            self.assertEqual([q["query"] for q in report[key]["queries"]], ["kept"])

    def test_excluded_reasons_are_exclusive_and_never_imputed(self):
        good = self.frame().iloc[0].to_dict()
        frame = pd.DataFrame([
            good, dict(good, query="timeout", correct=False, note="TIMEOUT", tm_on=None),
            dict(good, query="wrong", correct=False), dict(good, query="missing", tm_off=None),
            dict(good, query="zero", tm_on=0), dict(good, query="inf", tm_on=float("inf")),
            dict(good, query="overflow", tm_off=1e308, tm_on=1e-308),
            dict(good, query="marked_timeout", note="ON_TIMEOUT"),
        ])
        report = STATS.build_statistics(frame)
        summary = report["groups"][0]
        counts = summary["counts"]
        self.assertEqual([counts[key] for key in ("total", "valid", "excluded", "timeouts")], [8, 1, 7, 2])
        self.assertEqual(counts["correctness_not_true"], 1)
        self.assertEqual(counts["missing_or_invalid_timing"], 3)
        self.assertEqual(counts["nonfinite_or_nonpositive_ratio"], 1)
        self.assertEqual(summary["totals"]["off_s"], 1)
        self.assertEqual(summary["speedup"]["min"], 0.5)
        self.assertIsNone(summary["speedup"]["stddev"])
        self.assertTrue(all(row["speedup"] is None for row in report["queries"][1:]))
        json.dumps(report, allow_nan=False)

    def test_fallback_skip_is_excluded_from_measured_statistics(self):
        measured = self.frame().iloc[0].to_dict()
        fallback = dict(
            measured,
            query="fallback",
            selected_plan="DUCKDB",
            correct="SKIPPED",
            note="FALLBACK-SKIP",
            timing_status="fallback-skip",
            tm_off=None,
            tm_on=None,
            tm_speedup=1.0,
        )
        report = STATS.build_statistics(pd.DataFrame([measured, fallback]))
        summary = next(
            row for row in report["groups"]
            if row["subset"] == "all" and row["scope"] == "overall"
        )
        self.assertEqual(summary["counts"]["valid"], 1)
        self.assertEqual(summary["counts"]["measured"], 1)
        self.assertEqual(summary["counts"]["fallback_skips"], 1)
        self.assertEqual(summary["counts"]["equal"], 0)
        self.assertEqual(summary["totals"]["off_s"], measured["tm_off"])
        self.assertEqual(summary["totals"]["on_s"], measured["tm_on"])
        fallback_row = next(row for row in report["queries"] if row["query"] == "fallback")
        self.assertIsNone(fallback_row["speedup"])
        self.assertEqual(fallback_row["speedup_source"], "not-measured")
        self.assertFalse(fallback_row["valid_timing"])
        self.assertFalse(fallback_row["valid_speedup"])

        # Passing equivalence does not turn a fallback's placeholder into a measurement.
        verified = dict(fallback, correct="TRUE", correctness_check="enabled")
        verified_rows = STATS.prepare_queries(pd.DataFrame([measured, verified]), "tm")
        checked_fallback = verified_rows.loc[verified_rows["query"].eq("fallback")].iloc[0]
        self.assertFalse(checked_fallback["valid_timing"])
        self.assertEqual(checked_fallback["speedup_source"], "not-measured")

    def test_correctness_timeout_status_is_excluded_as_timeout(self):
        good = self.frame().iloc[0].to_dict()
        frame = pd.DataFrame([
            good,
            dict(good, query="timeout", correct="TIMEOUT", note="TIMEOUT", tm_on=None,
                 relation_count=5, workload_category="v2", tree_shape="bushy"),
            dict(good, query="wrong", correct="FALSE", note="NOT-EQUIV"),
        ])
        report = STATS.build_statistics(frame)
        counts = report["groups"][0]["counts"]
        self.assertEqual(counts["valid"], 1)
        self.assertEqual(counts["timeouts"], 1)
        self.assertEqual(counts["correctness_not_true"], 1)
        timeout = next(row for row in report["queries"] if row["query"] == "timeout")
        self.assertEqual(timeout["correct"], "TIMEOUT")
        self.assertEqual(timeout["exclusion_reason"], "timeout")
        self.assertIsNone(timeout["speedup"])
        self.assertEqual(report["timeouts"]["limit_seconds"], 600)
        self.assertEqual(report["timeouts"]["total"], 1)
        self.assertEqual(report["timeouts"]["selected_plan_counts"], {"OUTERYAN": 1})
        relation = next(row for row in report["timeouts"]["distribution"]
                        if row["dimension"] == "relation_count" and row["value"] == "5")
        self.assertEqual((relation["timeout_queries"], relation["total_queries"]), (1, 1))

    def test_empty_statistics_and_timeout_only_shape_are_unavailable(self):
        frame = self.frame().iloc[:1].assign(correct=False, note="TIMEOUT", tm_on=None)
        report = STATS.build_statistics(frame)
        for group in report["groups"]:
            self.assertEqual(group["counts"]["valid"], 0)
            self.assertIsNone(group["speedup"]["geomean"])
            self.assertIsNone(group["totals"]["speedup"])
            self.assertEqual(group["speedup"]["min_queries"], [])
        self.assertTrue(any(group["scope"] == "benchmark_shape" for group in report["groups"]))

    def test_plan_subsets_and_group_totals_reconcile(self):
        report = STATS.build_statistics(self.frame())
        overall = {group["subset"]: group for group in report["groups"] if group["scope"] == "overall"}
        self.assertEqual(overall["outeryan_selected"]["counts"]["valid"], 2)
        self.assertEqual(overall["duckdb_selected"]["counts"]["valid"], 1)
        for subset, summary in overall.items():
            groups = [row for row in report["groups"] if row["subset"] == subset and row["scope"] == "benchmark_shape"]
            self.assertEqual(sum(row["counts"]["valid"] for row in groups), summary["counts"]["valid"])
            self.assertAlmostEqual(sum(row["totals"]["off_s"] for row in groups), summary["totals"]["off_s"])

    def test_workload_components_are_reported_when_provenance_is_available(self):
        frame = self.frame()
        frame["workload_component"] = ["structural", "structural", "evaluation"]
        report = STATS.build_statistics(frame)
        components = {
            group["workload_component"]: group
            for group in report["groups"]
            if group["subset"] == "all" and group["scope"] == "workload_component"
        }
        self.assertEqual(components["structural"]["counts"]["valid"], 2)
        self.assertEqual(components["evaluation"]["counts"]["valid"], 1)
        self.assertEqual(components["evaluation"]["totals"]["speedup"], 2)
        self.assertIn("Workload-component breakdown", STATS.markdown_report(report))

    def test_duplicate_or_mixed_thread_data_is_rejected(self):
        frame = self.frame()
        with self.assertRaisesRegex(ValueError, "deduplicate"):
            STATS.build_statistics(pd.concat([frame, frame.iloc[:1]], ignore_index=True))
        frame.loc[1, "timing_threads"] = 16
        with self.assertRaisesRegex(ValueError, "thread count"):
            STATS.build_statistics(frame)
        frame.loc[1, "run"] = "20260908_235240_t16"
        with self.assertRaisesRegex(ValueError, "one logical run"):
            STATS.build_statistics(frame)

    def test_index_alignment_and_missing_rounded_speedups(self):
        frame = self.frame().drop(columns="tm_speedup")
        frame.index = [12, 4, 19]
        report = STATS.build_statistics(frame)
        self.assertEqual([row["speedup"] for row in report["queries"]], [0.5, 1, 2])
        self.assertEqual(report["groups"][0]["counts"]["valid"], 3)

    def test_export_json_and_markdown_with_source_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "experiment_onoff_test.csv"
            self.frame().to_csv(source, index=False)
            report = STATS.write_statistics(root, self.frame(), sources=[str(source)])
            saved = json.loads((root / "statistics.json").read_text())
            self.assertEqual(saved, report)
            self.assertEqual(report["input_rows"], 3)
            self.assertEqual(len(report["sources"][0]["sha256"]), 64)
            markdown = (root / "STATISTICS.md").read_text()
            for text in ("Geomean", "Percentiles", "OFF/ON runtime", "Shape breakdown", "Extreme queries",
                         "Phase-profile statistics", "Sources"):
                self.assertIn(text, markdown)
            self.assertNotIn("nan", markdown)
            # All Markdown tables must have matching header/separator/data widths.
            width = None
            for line in markdown.splitlines():
                if line.startswith("|"):
                    count = line.count("|")
                    if width is None:
                        width = count
                    self.assertEqual(count, width, line)
                else:
                    width = None

    def test_phase_profiles_are_separate_cpu_work_and_wall_latency(self):
        frame = self.frame()
        timeout = frame.iloc[[0]].assign(query="profile_timeout", correct=False, note="TIMEOUT")
        frame = pd.concat([frame, timeout], ignore_index=True)
        frame["profile_status"] = ["OK", "not-selected", "OK", "OK"]
        frame["profile_threads"] = 32
        frame["profile_wall_time_s"] = [2, None, 4, 100]
        frame["profile_cpu_time_s"] = [10, None, 20, 100]
        frame["profile_round1_operator_s"] = [1, None, 4, 25]
        frame["profile_round2_operator_s"] = [2, None, 4, 25]
        frame["profile_round3_operator_s"] = [3, None, 6, 25]
        frame["profile_other_elapsed_s"] = [4, None, 6, 25]
        report = STATS.build_statistics(frame)
        phase = report["phase_profiles"]
        self.assertTrue(phase["available"])
        self.assertEqual(len(phase["queries"]), 2)
        overall = phase["groups"][0]
        self.assertEqual(overall["cpu_total_s"], 30)
        self.assertAlmostEqual(overall["cpu_weighted_fraction"]["round1"], 5 / 30)
        self.assertAlmostEqual(overall["cpu_weighted_fraction"]["other"], 10 / 30)
        self.assertEqual(overall["profile_wall_s"]["median"], 3)
        self.assertEqual(overall["unprofiled_speedup"]["median"], 1.25)

    def test_optimizer_totals_and_workflow_phases_are_exported(self):
        frame = self.frame()
        frame["workload_category"] = ["v1", "v1", "v3_aggregation"]
        frame["optimizer_profile_status"] = "OK"
        frame["optimizer_timed_samples"] = 1
        frame["optimizer_duckdb_total_s"] = [1.0, 2.0, 4.0]
        frame["optimizer_outeryan_total_s"] = [1.5, 2.2, 5.0]
        frame["optimizer_overhead_s"] = [0.5, 0.2, 1.0]
        frame["optimizer_outeryan_to_duckdb_ratio"] = [1.5, 1.1, 1.25]
        frame["optimizer_duckdb_measured_phase_s"] = [0.9, 1.8, 3.6]
        frame["optimizer_outeryan_measured_phase_s"] = [1.35, 1.98, 4.5]
        frame["optimizer_duckdb_other_s"] = [0.1, 0.2, 0.4]
        frame["optimizer_outeryan_other_s"] = [0.15, 0.22, 0.5]
        frame["optimizer_duckdb_phases_json"] = [
            json.dumps({"duckdb_join_reorder": value, "desimplification": 0.0})
            for value in (0.4, 0.8, 1.6)
        ]
        frame["optimizer_outeryan_phases_json"] = [
            json.dumps({"duckdb_join_reorder": value, "desimplification": phase})
            for value, phase in ((0.4, 0.2), (0.8, 0.3), (1.6, 0.8))
        ]
        frame["optimizer_phase_delta_json"] = "{}"
        report = STATS.build_statistics(frame)
        optimizer = report["optimizer_profiles"]
        self.assertTrue(optimizer["available"])
        overall = [row for row in optimizer["groups"]
                   if row["subset"] == "all" and row["scope"] == "overall"][0]
        self.assertEqual(overall["profiles"], 3)
        self.assertEqual(overall["duckdb_s"]["median"], 2)
        self.assertAlmostEqual(overall["totals"]["outeryan_to_duckdb_ratio"], 8.7 / 7)
        self.assertEqual(len(optimizer["phases"]), 6)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            STATS.write_statistics(root, frame)
            benchmark = pd.read_csv(root / "benchmark_statistics.csv")
            self.assertTrue({"all", "outeryan_selected"}.issubset(set(benchmark["subset"])))
            self.assertTrue({"min", "max", "geomean", "median", "stddev"}.issubset(benchmark.columns))
            optimizer_summary = pd.read_csv(root / "optimizer_summary.csv")
            self.assertIn("ratio_median", optimizer_summary.columns)
            optimizer_phases = pd.read_csv(root / "optimizer_phases.csv")
            self.assertEqual(
                set(optimizer_phases["phase"]), {"duckdb_join_reorder", "desimplification"}
            )
            optimizer_phase_summary = pd.read_csv(root / "optimizer_phase_summary.csv")
            self.assertIn("delta_median", optimizer_phase_summary.columns)
            self.assertTrue((root / "timeout_summary.csv").exists())
            self.assertTrue((root / "timeout_queries.csv").exists())
            self.assertTrue((root / "strata_statistics.csv").exists())


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
                "selected_plan": "OUTERYAN",
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

    def test_unresolved_sql_is_not_assumed_equal_from_names(self):
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
        self.assertEqual(loaded["run"].unique().tolist(), ["20260925_120000_t32"])
        self.assertEqual(len(loaded), 2)
        self.assertEqual(set(loaded["workload_category"]), {"join"})
        self.assertEqual(set(loaded["original_workload_category"]), {"v1", "v2"})

    def test_sql_dedup_merges_aliases_but_preserves_literals_and_latest_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            scripts = Path(folder)
            root = scripts / "outerjoin_benchmark"
            (root / "benchmark/tpch").mkdir(parents=True)
            (root / "v2/benchmark/tpch").mkdir(parents=True)
            (root / "benchmark/tpch/old.sql").write_text("SELECT * FROM t WHERE name='A';")
            (root / "v2/benchmark/tpch/new.sql").write_text("-- renamed\nselect * FROM t WHERE name = 'A';")
            (root / "v2/benchmark/tpch/different.sql").write_text("SELECT * FROM t WHERE name='a';")
            frame = pd.DataFrame([
                dict(query="old", workload_category="v1", family="tpch", sql_path="tpch/old.sql", correct="TRUE"),
                dict(query="new", workload_category="v2", family="tpch", sql_path="tpch/new.sql", correct="TIMEOUT"),
                dict(query="different", workload_category="v2", family="tpch", sql_path="tpch/different.sql", correct="TRUE"),
            ])
            with mock.patch.object(PLOT, "SCRIPT_DIR", scripts):
                result = PLOT.deduplicate_sql_results(frame)
                repeated = PLOT.deduplicate_sql_results(result)
                self.assertEqual(result["query"].tolist(), repeated["query"].tolist())
                self.assertEqual(result["sql_identity"].tolist(), repeated["sql_identity"].tolist())
            self.assertEqual(result["original_query"].tolist(), ["new", "different"])
            self.assertEqual(result.iloc[0]["correct"], "TIMEOUT")
            self.assertEqual(result["sql_identity"].nunique(), 2)

    def test_version_suffixes_preserve_timestamp_and_threads(self):
        for suffix in ("v1", "v2", "v3", "v3_selectivity_stress", "all"):
            self.assertEqual(
                PLOT.result_source(f"experiment_onoff_benchmark_20260926_110332_t32_{suffix}.csv"),
                ("20260926_110332_t32", "final", "benchmark"),
            )

    def test_date_merge_preserves_versions_and_keeps_latest_failure(self):
        base = {"query": "same", "family": "tpch", "correct": "TRUE", "timing_threads": 32,
                "tm_off": 2, "tm_on": 1, "tm_speedup": 2}
        prefix = "experiment_onoff_benchmark_20260926_"
        sources = {
            prefix + "110332_t32_v1.csv": pd.DataFrame([base, dict(base, query="older_only")]),
            prefix + "163933_t32_v1.csv": pd.DataFrame([dict(base, correct="TIMEOUT", note="TIMEOUT", tm_on=None)]),
            prefix + "110332_t32_v2.csv": pd.DataFrame([base]),
            prefix + "110332_t32_v3.csv": pd.DataFrame([base]),
            prefix + "110332_t32_v3_selectivity_stress.csv": pd.DataFrame([base]),
        }
        with mock.patch.object(PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()), \
                mock.patch.object(PLOT, "benchmark_provenance", side_effect=empty_benchmark_provenance):
            rows = PLOT.load(list(reversed(sources)), group_by="date", date="20260926")
        self.assertEqual(rows["run"].unique().tolist(), ["20260926_t32"])
        self.assertEqual(len(rows), 5)
        self.assertEqual(set(rows["workload_category"]), {"join", "aggregate"})
        latest = rows.loc[rows.original_workload_category.eq("v1") & rows["query"].eq("same")].iloc[0]
        self.assertEqual(latest["correct"], "TIMEOUT")
        self.assertEqual(latest["source_run"], "20260926_163933_t32")
        self.assertEqual(rows.loc[rows["query"].eq("older_only"), "source_run"].iloc[0], "20260926_110332_t32")

    def test_date_merge_never_combines_threads_or_other_dates(self):
        sources = {}
        for day in ("20260926", "20260927"):
            for threads in (16, 32):
                name = f"experiment_onoff_benchmark_{day}_110332_t{threads}_v1.csv"
                sources[name] = pd.DataFrame([{
                    "query": "same", "family": "job", "timing_threads": threads,
                    "experiment_group": day + "_110639", "tm_off": 2, "tm_on": 1,
                }])
        with mock.patch.object(PLOT.pd, "read_csv", side_effect=lambda path: sources[path].copy()), \
                mock.patch.object(PLOT, "benchmark_provenance", side_effect=empty_benchmark_provenance):
            rows = PLOT.load(list(sources), group_by="date", date="20260926")
            batches = PLOT.load(list(sources), group_by="run")
        self.assertEqual(set(rows["run"]), {"20260926_t16", "20260926_t32"})
        self.assertEqual(batches["run"].nunique(), 4)

    def test_disagreeing_thread_metadata_is_rejected(self):
        raw = pd.DataFrame([{"query": "q", "family": "job", "timing_threads": 16}])
        with mock.patch.object(PLOT.pd, "read_csv", return_value=raw):
            with self.assertRaisesRegex(ValueError, "thread counts disagree"):
                PLOT.load(["experiment_onoff_benchmark_20260926_110332_t32_v1.csv"], group_by="date")

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
        with mock.patch.object(Path, "read_text", return_value=sql), mock.patch.object(PLOT, "resolve_sql_path", return_value=Path("sample.sql")):
            enriched = PLOT.enrich(frame, "20260830_002656")
        self.assertEqual(enriched.iloc[0]["relation_count"], 3)

    def test_graph_scan_subqueries_count_base_relations_only(self):
        frame = pd.DataFrame([{
            "query": "graph__graph__sample__inputcap1__sel_high",
            "sql_path": "graph/sample.sql", "relation_count": 3,
        }])
        sql = ("SELECT * FROM R1 LEFT JOIN (SELECT src, dst FROM R2 WHERE src <= 40) R2 "
               "ON R1.dst=R2.src RIGHT JOIN (SELECT src, dst FROM R3 WHERE src <= 40) R3 "
               "ON R2.dst=R3.src")
        with mock.patch.object(Path, "read_text", return_value=sql), mock.patch.object(
                PLOT, "resolve_sql_path", return_value=Path("sample.sql")):
            enriched = PLOT.enrich(frame, "20261002_213551")
        self.assertEqual(enriched.iloc[0]["relation_count"], 3)


class PlotSpeedupPhaseTest(unittest.TestCase):
    def test_display_labels_preserve_statistics_family_keys(self):
        self.assertEqual(PLOT.figure_family_label("graph"), "SGPB")
        self.assertEqual(PLOT.figure_family_label("Graph"), "SGPB")
        self.assertEqual(PLOT.figure_family_label("TPC-H"), "TPC-H")
        self.assertEqual(PLOT.normalize_family("graph"), "Graph")
        self.assertIn("G=SGPB", PLOT.QUERY_CODE_KEY)
        self.assertEqual(
            [label for label, _, _, _ in PLOT.PHASES],
            ["Round 1", "Round 2", "Round 3", "Other OP"],
        )

    def test_sgpb_label_in_phase_figure(self):
        frame = pd.DataFrame([self.phase_row("graph_chain4_ld", "graph", 2.0, 3.0)])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_phase(object(), frame, "test")
        self.assertIn("SGPB", [text.get_text() for text in captured[0].axes[0].texts])
        plt.close(captured[0])

    def test_requested_footer_lines_are_absent_from_both_figures(self):
        frame = pd.DataFrame([dict(self.phase_row("q", "JOB", 10, 3), timing_threads=8)])
        figures = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: figures.append(fig)):
            PLOT.page_phase(object(), frame, "test")
            PLOT.page_speedup_scatter(object(), frame, "test", "tm")
        self.assertEqual(len(figures), 2)
        for figure in figures:
            labels = "\n".join(text.get_text() for text in figure.texts)
            self.assertNotIn("Sub-second measured pairs retained", labels)
            self.assertNotIn("bars sum to CPU time", labels)
            self.assertNotIn("right panel: measured OuterYan-selected", labels)
            self.assertNotIn("(2)", labels)
            plt.close(figure)

    def test_diverse_phase_sample_keeps_only_speedups_and_covers_phase_extremes(self):
        rows = []
        compositions = [(2.5, 2.5, 2.5, 2.5), (10, 0, 0, 0), (0, 10, 0, 0),
                        (0, 0, 10, 0), (0, 0, 0, 10), (2.4, 2.6, 2.5, 2.5)]
        for family in PLOT.FAMILY_ORDER:
            for index, composition in enumerate(compositions):
                row = dict(self.phase_row(f"q{index}", family, 10, 2), timing_threads=8)
                for (_, seconds, ratio, _), value in zip(PLOT.PHASES, composition):
                    row[seconds], row[ratio] = value, value / 10
                rows.append(row)
            rows.append(dict(rows[-1], query="slow", tm_off=.99, tm_on=1))
            rows.append(dict(rows[-1], query="invalid", tm_off=float("nan")))
        frame = pd.DataFrame(rows)
        sampled = PLOT.diverse_phase_samples(frame, 5, max_other_share=1.0)
        self.assertEqual(sampled.groupby("family").size().to_dict(), {f: 5 for f in PLOT.FAMILY_ORDER})
        self.assertTrue((sampled.tm_off / sampled.tm_on).ge(1).all())
        for family in PLOT.FAMILY_ORDER:
            self.assertEqual(set(sampled.loc[sampled.family.eq(family), "query"]), {f"q{i}" for i in range(5)})
        shuffled = PLOT.diverse_phase_samples(frame.sample(frac=1, random_state=42), 5, max_other_share=1.0)
        self.assertEqual(sampled[["family", "query"]].values.tolist(), shuffled[["family", "query"]].values.tolist())

    def test_phase_display_prefers_low_other_and_keeps_four_stable_ids(self):
        rows = []
        for family in PLOT.FAMILY_ORDER:
            others = [2, 5.4, 5.8, 6.3, 8.6] if family == "graph" else [1, 2, 3, 5, 8.4]
            for index, other in enumerate(others):
                row = dict(self.phase_row(f"q{index}", family, 10, 2), timing_threads=8,
                           short_query=f"original-{family}-{index}")
                for (_, seconds, ratio, _), value in zip(PLOT.PHASES, [0, 0, 10-other, other]):
                    row[seconds], row[ratio] = value, value / 10
                rows.append(row)
        frame = pd.DataFrame(rows)
        original = frame.copy(deep=True)
        sampled = PLOT.diverse_phase_samples(frame)
        self.assertEqual(sampled.groupby("family").size().to_dict(), {f: 4 for f in PLOT.FAMILY_ORDER})
        self.assertNotIn("q4", sampled["query"].values)
        self.assertTrue(sampled.loc[sampled.family.ne("graph"), "profile_other_ratio"].le(.5).all())
        self.assertTrue(sampled.loc[sampled.family.eq("graph"), "_phase_other_limit_relaxed"].all())
        self.assertTrue(sampled.short_query.str.startswith("original-").all())
        shuffled = PLOT.diverse_phase_samples(frame.sample(frac=1, random_state=42))
        self.assertEqual(sampled.short_query.tolist(), shuffled.short_query.tolist())
        pd.testing.assert_frame_equal(frame, original)
        for value in (-.1, 1.1, float("nan")):
            with self.assertRaisesRegex(ValueError, "share limit"):
                PLOT.diverse_phase_samples(frame, max_other_share=value)

    def test_short_phase_seconds_are_not_rounded_to_zero(self):
        self.assertEqual(PLOT.format_seconds_label(0.004174538), "0.0042s")

    def test_eight_phase_rows_keep_footer_clear_of_axis_labels(self):
        frame = pd.DataFrame([
            self.phase_row(f"q_{family}_{i}", family, 2, 3)
            for family in PLOT.FAMILY_ORDER for i in range(2)
        ])
        with mock.patch.object(PLOT, "save_page") as save:
            PLOT.page_phase(object(), frame, "test")
        figure = save.call_args.args[1]
        try:
            self.assertAlmostEqual(figure.get_figheight(), 3.27)
            self.assertAlmostEqual(figure.get_figwidth(), 15.1)
            figure.canvas.draw()
            renderer = figure.canvas.get_renderer()
            footer = next(text for text in figure.texts if text.get_text() == PLOT.QUERY_CODE_KEY)
            gaps = [axis.xaxis.label.get_window_extent(renderer).y0
                    - footer.get_window_extent(renderer).y1 for axis in figure.axes]
            self.assertAlmostEqual(min(gaps), 3 * figure.dpi / 72)
        finally:
            plt.close(figure)

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
        self.assertEqual(labels, ["Q-H-LD-01", "Q-J-RD-01"])
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
        for prefix in ("derived", "stress"):
            tier_prefix = "sel" if prefix == "derived" else "stress"
            for tier in ("low", "medium", "high"):
                self.assertEqual(PLOT.topology_from_query(
                    f"{prefix}__sem__ojb_tpcds_q72_bdmx_{tier_prefix}_{tier}"), "bushy")
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

    def test_phase_summary_can_include_completed_on_profile_after_off_timeout(self):
        base = dict(self.phase_row("baseline_timeout", "graph", 2, 3),
                    correct="NOT-CHECKED", correctness_check="disabled", timing_status="timeout",
                    duckdb_status="timeout", outeryan_status="measured", profile_status="OK",
                    duckdb_timeout_stage="warmup", outeryan_timeout_stage="-", tm_off=math.nan,
                    note="TIMEOUT-OFF-WARMUP")
        frame = pd.DataFrame([base])
        self.assertTrue(PLOT.complete_phase_rows(frame)[0].empty)
        complete, rejected = PLOT.complete_phase_rows(frame, include_duckdb_timeouts=True)
        self.assertEqual((len(complete), rejected), (1, 0))
        self.assertAlmostEqual(complete.iloc[0]["_phase_sum_s"], 10)
        self.assertTrue(pd.isna(complete.iloc[0]["tm_off"]))
        # The paired figure must not turn the baseline limit into a measurement.
        self.assertTrue(PLOT.phase_baseline_rows(frame).empty)
        for changes in (
            dict(outeryan_status="timeout"), dict(outeryan_timeout_stage="timing"),
            dict(profile_status="timeout"), dict(correct="FALSE"), dict(correctness_check="enabled"),
            dict(outeryan_correctness_status="NOT-EQUIV"), dict(tm_on=math.nan),
            dict(selected_plan="DUCKDB"), dict(profile_round1_operator_s=999),
        ):
            with self.subTest(changes=changes):
                bad = pd.DataFrame([dict(base, **changes)])
                self.assertTrue(PLOT.complete_phase_rows(bad, include_duckdb_timeouts=True)[0].empty)

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

    def test_phase_pairing_keeps_same_query_in_different_versions_separate(self):
        frame = pd.DataFrame([
            dict(self.phase_row("same", "JOB", 2, baseline), workload_category=version, timing_threads=8)
            for version, baseline in (("v1", 3), ("v2", 7))
        ])
        sample, phases = PLOT.paired_representative_samples(frame, frame)
        self.assertEqual(len(sample), 2)
        self.assertEqual(len(phases), 2)
        self.assertEqual(phases.set_index("workload_category")["baseline_time_s"].to_dict(), {"v1": 3, "v2": 7})
        self.assertEqual(sample["short_query"].nunique(), 2)
        self.assertTrue(sample["short_query"].str.startswith("Q-J-").all())
        self.assertFalse(sample["short_query"].str.contains(r"-V[123]-").any())
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_phase(object(), phases, "20260926_t8", preselected=True)
        figure = captured[0]
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        axis = figure.axes[0]
        family_label = next(text for text in axis.texts if text.get_text() == "JOB")
        self.assertLess(family_label.get_window_extent(renderer).x1,
                        min(label.get_window_extent(renderer).x0 for label in axis.get_yticklabels()))
        plt.close(figure)

    def test_subsecond_pairs_are_removed_from_all_plot_populations(self):
        frame = pd.DataFrame([
            dict(self.phase_row(name, "JOB", 2, off), tm_on=on, timing_threads=8,
                 correct="TRUE", tm_speedup=off / on)
            for name, off, on in (("short_win", 0.8, 0.2), ("short_loss", 0.2, 0.8),
                                  ("off_boundary", 1.0, 0.2), ("on_boundary", 0.2, 1.0))
        ])
        expected = {"off_boundary", "on_boundary"}
        for rows in (PLOT.timed(frame), PLOT.positive_runtime_rows(frame, "tm"),
                     PLOT.complete_runtime_rows(frame), PLOT.complete_phase_rows(frame)[0]):
            self.assertEqual(set(rows["query"]), expected)
        sample, phases = PLOT.paired_representative_samples(frame, frame)
        self.assertEqual(set(sample["query"]), expected)
        self.assertEqual(set(phases["query"]), expected)
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_speedup_scatter(object(), frame, "test", "tm")
        points = [tuple(point) for collection in captured[0].axes[0].collections
                  if collection.__class__.__name__ == "PathCollection"
                  for point in collection.get_offsets().tolist()]
        self.assertEqual(set(points), {(1.0, 0.2), (0.2, 1.0)})
        plt.close(captured[0])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            stale = ("speedup_all_queries.pdf", "speedup_all_queries.png",
                     "phase_breakdown_outeryan.pdf", "phase_breakdown_outeryan.png", "phase_queries.json")
            for name in stale:
                (output / name).write_text("old unfiltered result")
            paths = PLOT.write_standalone_runtime_figures(output, frame.iloc[:2], "test", "tm")
            self.assertEqual(paths, [])
            self.assertTrue(all(not (output / name).exists() for name in stale))

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

    def test_large_speedup_outlier_has_readable_decade_ticks(self):
        frame = pd.DataFrame([
            self.runtime_row("one", "graph", "OUTERYAN", 1.2, 0),
            self.runtime_row("outlier", "graph", "OUTERYAN", 7743.112, 1),
        ])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_speedup_scatter(object(), frame, "test", "tm")
        axis = captured[0].axes[1]
        self.assertIn("1000×", [tick.get_text() for tick in axis.get_xticklabels()])
        self.assertEqual([tick.get_text() for tick in axis.get_yticklabels()], ["SGPB"])
        self.assertIn("SGPB", [text.get_text() for text in captured[0].legends[0].get_texts()])
        self.assertGreaterEqual(axis.get_xlim()[1], math.log10(7743.112))
        plt.close(captured[0])

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

    def test_right_panel_keeps_only_measured_outeryan_plans_including_equal_and_slower(self):
        base = self.runtime_row("equal", "TPC-H", "OUTERYAN", 1.0, 0.0)
        frame = pd.DataFrame([
            base,
            self.runtime_row("slower", "TPC-H", "OUTERYAN", 0.5, 0.0),
            self.runtime_row("duckdb_equal", "JOB", "DUCKDB", 1.0, 0.0),
            self.runtime_row("duckdb_faster", "JOB", "DUCKDB", 2.0, 0.0),
            dict(base, query="short", tm_off=0.8, tm_on=0.2),
            dict(base, query="failed", correct="FALSE"),
            *[dict(base, query=f"fallback_{plan}", selected_plan=plan,
                   correct="SKIPPED", note="FALLBACK-SKIP", timing_status="fallback-skip",
                   tm_off=float("nan"), tm_on=float("nan"))
              for plan in ("DUCKDB", "OUTERYAN")],
        ])
        frame["correct"] = frame["correct"].fillna("TRUE")
        frame["tm_speedup"] = 999  # Rendered values must come from measured runtimes.
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)), \
                mock.patch.object(PLOT, "speedup_distribution", wraps=PLOT.speedup_distribution) as draw:
            PLOT.page_speedup_scatter(object(), frame, "test", "tm")
        distribution, families = draw.call_args.args[1:]
        self.assertEqual(distribution["query"].tolist(), ["equal", "slower"])
        self.assertEqual(distribution["_speedup"].tolist(), [1.0, 0.5])
        self.assertEqual(families, ["TPC-H"])
        left = captured[0].axes[0]
        points = [point for collection in left.collections
                  if collection.__class__.__name__ == "PathCollection"
                  for point in collection.get_offsets()]
        self.assertEqual(len(points), 4)
        plt.close(captured[0])

    def test_right_panel_handles_no_measured_outeryan_plan(self):
        frame = pd.DataFrame([self.runtime_row("duckdb", "JOB", "DUCKDB", 1.0, 0.0)])
        captured = []
        with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
            PLOT.page_speedup_scatter(object(), frame, "test", "tm")
        right = captured[0].axes[1]
        self.assertEqual(len(right.collections), 0)
        self.assertIn("No measured OuterYan-selected queries", [text.get_text() for text in right.texts])
        plt.close(captured[0])

    def test_speedup_colorbar_matches_background_and_includes_equal_reference(self):
        for speedups in ([0.5, 1.0, 100.0], [2.0, 4.0], [0.25, 0.5], [1.0]):
            with self.subTest(speedups=speedups):
                frame = pd.DataFrame([
                    self.runtime_row(f"q{index}", "JOB", "OUTERYAN", ratio, 0.0)
                    for index, ratio in enumerate(speedups)
                ])
                captured = []
                with mock.patch.object(PLOT, "save_page", side_effect=lambda _, fig: captured.append(fig)):
                    PLOT.page_speedup_scatter(object(), frame, "test", "tm")
                figure = captured[0]
                right = figure.axes[1]
                background = right.images[0]
                colorbar = background.colorbar
                self.assertIs(colorbar.mappable, background)
                self.assertEqual(tuple(background.get_extent()[:2]), right.get_xlim())
                self.assertLess(right.get_xlim()[0], 0.0)
                self.assertGreater(right.get_xlim()[1], 0.0)
                # Both hues fade to white at the equal-speed reference,
                # including when all measured queries lie on the same side.
                self.assertTrue(all(channel > 0.995 for channel in background.to_rgba(0.0)[:3]))
                self.assertEqual(colorbar.get_ticks().tolist(), [])
                self.assertEqual(colorbar.ax.get_title(), "")
                for bar_limit, plot_limit in zip(colorbar.ax.get_xlim(), right.get_xlim()):
                    self.assertAlmostEqual(bar_limit, plot_limit)
                figure.canvas.draw()
                left_box, right_box = [axis.get_position() for axis in figure.axes]
                bar_box = colorbar.ax.get_position()
                self.assertAlmostEqual(left_box.y0, right_box.y0)
                self.assertLess(right_box.y1, left_box.y1)
                self.assertAlmostEqual(bar_box.x0, right_box.x0)
                self.assertAlmostEqual(bar_box.x1, right_box.x1)
                self.assertGreater(bar_box.y0, right_box.y1)
                self.assertAlmostEqual(bar_box.y1, left_box.y1)
                arrow = next(patch for patch in colorbar.ax.patches
                             if patch.__class__.__name__ == "Polygon")
                vertices = arrow.get_transform().transform(arrow.get_xy())
                shaft_left = vertices[PLOT.np.isclose(vertices[:, 0], colorbar.ax.bbox.x0)]
                self.assertAlmostEqual(shaft_left[:, 1].max(), figure.axes[0].bbox.y1)
                direction_labels = [text for text in right.texts
                                    if text.get_text() in ("OuterYan slower", "OuterYan faster")]
                self.assertEqual(len(direction_labels), 2)
                self.assertTrue(all(text.get_window_extent().y0 > colorbar.ax.bbox.y1
                                    for text in direction_labels))
                captions = [text for axis in figure.axes for text in axis.texts
                            if text.get_text().startswith(("(a)", "(b)"))]
                self.assertAlmostEqual(captions[0].get_window_extent().y0,
                                       captions[1].get_window_extent().y0)
                plt.close(figure)

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

    def test_fallback_skip_is_excluded_from_speedup_plots(self):
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
        frame["correct"] = frame["correct"].fillna("TRUE")
        self.assertEqual(PLOT.timed(frame)["query"].tolist(), ["derived__measured"])
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


def install_sql_metadata_fixture(testcase):
    scratch = tempfile.TemporaryDirectory()
    testcase.addCleanup(scratch.cleanup)
    path = Path(scratch.name) / "query.sql"
    path.write_text("SELECT a.value FROM ta a JOIN tb b ON a.id=b.id "
                    "LEFT JOIN tc c ON b.id=c.id WHERE c.flag=1")
    schema = {"database": "fixture", "tables": {"ta": ["id", "value"], "tb": ["id"], "tc": ["id", "flag"]}}
    for patcher in (mock.patch.object(RESULT, "query_sql_path", return_value=path),
                    mock.patch.object(RESULT, "database_columns", return_value=schema)):
        patcher.start()
        testcase.addCleanup(patcher.stop)


class ReportMetadataTest(unittest.TestCase):
    def test_plain_report_numbers_have_no_latex_markup(self):
        self.assertEqual(PAPER.number(None), "--")
        self.assertEqual(PAPER.number(math.nan), "--")
        self.assertEqual(PAPER.number(math.inf), "--")
        self.assertEqual(PAPER.number(1.25), "1.2500")
        self.assertEqual(PAPER.number(12, 0), "12")

    def setUp(self):
        install_sql_metadata_fixture(self)

    @staticmethod
    def frame():
        rows = []
        for family in ("graph", "TPC-H", "TPC-DS", "JOB"):
            for index, (off, on, plan) in enumerate(((4, 2, "OUTERYAN"), (1, 2, "OUTERYAN"), (2, 2, "DUCKDB"), (0.2, 0.8, "OUTERYAN"))):
                rows.append({
                    "run": "20260926_t32", "workload_category": "v1", "family": family,
                    "query": f"{family}_query_{index}", "topology": "left-deep", "tree_shape": "left-deep",
                    "join_graph_topology": "star", "join_type_composition": "I1-L1-R0-F0",
                    "selectivity_level": "0.1%", "workload_component": "structural",
                    "correct": "TRUE", "note": "OK", "timing_status": "ok", "timing_threads": 32,
                    "selected_plan": plan, "tm_off": off, "tm_on": on, "tm_speedup": 999,
                    "relation_count": 3, "optimizer_profile_status": "OK", "optimizer_timed_samples": 1,
                    "optimizer_duckdb_total_s": 0.01, "optimizer_outeryan_total_s": 0.04,
                    "optimizer_duckdb_phases_json": "{}", "optimizer_outeryan_phases_json": "{}",
                    "profile_status": "OK", "profile_wall_time_s": on, "profile_cpu_time_s": off * 10,
                    "profile_round1_operator_s": off, "profile_round2_operator_s": off * 2,
                    "profile_round3_operator_s": off * 3, "profile_other_elapsed_s": off * 4,
                })
        rows.extend([
            dict(rows[0], query="unexecuted", correct="SKIPPED", note="FALLBACK-SKIP",
                 timing_status="fallback-skip", selected_plan="DUCKDB", tm_off=None, tm_on=None,
                 workload_component="evaluation"),
            dict(rows[0], query="timeout", correct="TIMEOUT", note="TIMEOUT", tm_off=None, tm_on=None,
                 workload_component="selectivity_ablation", workload_category="v3_selectivity_stress"),
        ])
        return pd.DataFrame(rows)

    def report(self, frame=None, **kwargs):
        frame = self.frame() if frame is None else frame
        return PAPER.build_report_metadata(frame, STATS.build_statistics(frame), **kwargs)

    def test_all_populations_threshold_and_formulas(self):
        report = self.report()
        corpus = report["corpus"]
        self.assertEqual((corpus["structural"], corpus["supplementary"], corpus["total"]), (12, 0, 12))
        self.assertEqual(corpus["selectivity_ablation"], 0)
        self.assertEqual(report["input_corpus"]["total"], 18)
        self.assertEqual(report["coverage"]["both_runtimes_below_1s"], 4)
        all_rows = report["runtime"]["all"][-1]
        selected = report["runtime"]["outeryan_selected"][-1]
        self.assertEqual(all_rows["counts"]["valid"], 12)
        self.assertEqual(all_rows["counts"]["measured"], 12)
        self.assertEqual(selected["counts"]["valid"], 8)
        self.assertAlmostEqual(all_rows["speedup"]["geomean"], 1)
        self.assertAlmostEqual(all_rows["totals"]["speedup"], 28 / 24)
        self.assertEqual(report["phase"][-1]["profiles"], 8)
        self.assertAlmostEqual(report["phase"][-1]["cpu_weighted_fraction"]["round2"], 0.2)
        self.assertEqual(len(report["representatives"]), 8)
        for row in report["representatives"]:
            self.assertEqual(row["duckdb_optimizer_ms"], 10)
            self.assertEqual(row["outeryan_optimizer_ms"], 40)
            self.assertAlmostEqual(row["duckdb_optimizer_percent"], 1 / row["duckdb_s"])
            self.assertEqual(row["outeryan_optimizer_percent"], 2)
            self.assertEqual(row["attribute_count"], 5)
        self.assertEqual(report["runtime"]["all"][-1]["counts"]["fallback_skips"], 0)

    def test_unchecked_runtime_profiles_remain_explicit_in_metadata(self):
        frame = self.frame().iloc[:16].copy()
        frame["correct"] = "NOT-CHECKED"
        frame["correctness_check"] = "disabled"
        frame["timing_status"] = "measured"
        report = self.report(frame)
        self.assertEqual(report["coverage"]["unchecked_measured"], 12)
        self.assertEqual(report["phase"][-1]["profiles"], 8)
        self.assertEqual(len(report["representatives"]), 8)
        self.assertEqual(report["coverage"]["measured"], report["coverage"]["unchecked_measured"])

    def test_cpu_weighting_is_not_mean_of_query_percentages(self):
        frame = self.frame().iloc[:2].copy()
        for index, (cpu, parts) in enumerate(((10, (10, 0, 0, 0)), (90, (0, 90, 0, 0)))):
            frame.loc[index, "profile_cpu_time_s"] = cpu
            for (_, column), value in zip(STATS.PHASE_COMPONENTS, parts):
                frame.loc[index, column] = value
        phase = self.report(frame)["phase"][-1]
        self.assertAlmostEqual(phase["cpu_weighted_fraction"]["round1"], 0.1)
        self.assertAlmostEqual(phase["cpu_weighted_fraction"]["round2"], 0.9)

    def test_overview_uses_only_measured_outeryan_and_counts_only_valid_queries(self):
        frame = self.frame().iloc[:3].copy()
        frame["tm_off"] = [4, 8, 200]
        fallback = dict(frame.iloc[0], query="fallback_selected", tm_off=None, tm_on=None,
                        correct="SKIPPED", timing_status="fallback-skip", note="FALLBACK-SKIP")
        frame = pd.concat([frame, pd.DataFrame([fallback])], ignore_index=True)
        report = self.report(frame)
        self.assertEqual(report["corpus"]["total"], 3)
        self.assertEqual(report["input_corpus"]["total"], 4)
        overview = report["runtime"]["outeryan_selected"][-1]
        self.assertEqual(overview["counts"]["valid"], 2)
        self.assertAlmostEqual(overview["speedup"]["geomean"], math.sqrt(8))
        statistics = STATS.build_statistics(frame)
        self.assertEqual(statistics["valid_queries"], 3)
        self.assertEqual(statistics["headline"]["counts"]["valid"], 2)
        self.assertAlmostEqual(statistics["headline"]["speedup"]["geomean"], math.sqrt(8))

    def test_selection_does_not_rank_speedup_and_missing_profiles_are_excluded(self):
        frame = self.frame()
        first = PAPER.representatives(frame, STATS.prepare_queries(frame, "tm"), 1)
        frame.loc[frame["tm_off"].ge(1), "tm_on"] *= 100
        second = PAPER.representatives(frame, STATS.prepare_queries(frame, "tm"), 1)
        self.assertEqual([row["query"] for row in first], [row["query"] for row in second])
        frame["optimizer_profile_status"] = "ERROR"
        self.assertEqual(PAPER.representatives(frame, STATS.prepare_queries(frame, "tm"), 3), [])
        self.assertEqual(self.report(frame)["representatives"], [])

    def test_metadata_only_and_original_data_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.csv"
            frame = self.frame()
            frame.to_csv(source, index=False)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            out = root / "out"
            result = PAPER.write_report_metadata(out, frame, [str(source)])
            self.assertFalse(list(out.glob("*.tex")))
            self.assertEqual(result["sources"][0]["sha256"], digest)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            saved = json.loads((out / "report_metadata.json").read_text())
            self.assertEqual(saved["coverage"]["measured"], 12)
            self.assertEqual(saved, result)
            # Existing user-authored manuscript files are not modified or removed.
            manuscript = out / "notes.tex"
            manuscript.write_text("user manuscript")
            PAPER.write_report_metadata(out, frame, [str(source)])
            self.assertEqual(manuscript.read_text(), "user manuscript")

    def test_real_manifest_roles_and_distinct_dimensions(self):
        provenance = PLOT.benchmark_provenance()
        recovery = provenance[provenance["evaluation_role"].eq("historical_selectivity_recovery")]
        self.assertEqual(len(recovery), 54)
        self.assertEqual(set(recovery["workload_component"]), {"historical_recovery"})
        self.assertEqual(set(recovery["filter_design_revision"]), {"tpcds-recovery-20261005"})
        composition = PAPER.composition(recovery)
        self.assertEqual(composition["historical_recovery"], 54)
        self.assertEqual(composition["supplementary"], 54)
        self.assertEqual(composition["unclassified"], 0)
        supplementary = provenance[provenance["evaluation_role"].eq("historical_slow_baseline_case")]
        self.assertEqual(len(supplementary), 3)
        self.assertEqual(set(supplementary["workload_component"]), {"evaluation"})
        self.assertEqual(set(supplementary["selectivity_level"]), {"Legacy modulo (unverified)"})
        historical = provenance[provenance["filter_design_revision"].isna()]
        self.assertEqual(len(historical), 932)
        # Historical definitions remain resolvable after retirement/replacement;
        # composition counts must use active identities rather than that union.
        active = pd.read_csv(PLOT.SCRIPT_DIR / "outerjoin_benchmark/benchmark/manifest.csv")
        self.assertEqual(len(active), 321)
        provenance = provenance[provenance["query_id"].isin(active["query_id"])]
        self.assertEqual(len(provenance), len(active))
        provenance = provenance[provenance["filter_design_revision"].isin(
            ["balanced-screened-20261002", "balanced-screened-20261002/inputcap1",
             "tpch-query-tuning-20261012", "cohort-selectivity-20261015"])]
        counts = provenance["workload_component"].value_counts().to_dict()
        # Frozen 321-query cohort; the revision filter above covers 280 identities.
        self.assertEqual(counts, {"structural": 201, "evaluation": 79})
        capped = provenance[provenance["graph_filter_revision"].eq("inputcap1")]
        self.assertEqual(len(capped), 67)
        self.assertTrue(capped["input_filter_placement"].eq("base_relation_subquery").all())
        self.assertTrue(capped["input_filter_profiles_json"].map(lambda value: len(json.loads(value)) in (3, 4)).all())
        stress = PLOT.benchmark_provenance().loc[lambda frame: frame["workload_category"].eq("v3_selectivity_stress") & frame["filter_design_revision"].notna()]
        self.assertEqual(len(stress), 18)
        self.assertEqual(stress["selectivity_level"].nunique(), 3)
        self.assertEqual(set(stress["tree_shape"]), {"left-deep", "right-deep", "bushy"})
        self.assertEqual(set(stress["join_graph_topology"]), {"chain", "star", "branch"})
        groups = STATS.build_statistics(self.frame())["groups"]
        self.assertEqual(next(row for row in groups if row["subset"] == "all" and row["scope"] == "join_graph_topology")["join_graph_topology"], "star")



class QueryAttributesTest(unittest.TestCase):
    schema = {"ta": ["id", "value"], "tb": ["id", "flag"]}

    def test_historical_measurements_resolve_to_their_original_sql_hashes(self):
        root = RESULT.SCRIPT_DIR / "outerjoin_benchmark" / "revisions" / "pre_semantic_20260925"
        checked = 0
        for category, scope in (("v1", "benchmark"), ("v2", "v2/benchmark"),
                                ("v3_aggregation", "v3/benchmark"),
                                ("v3_selectivity_stress", "v3/selectivity_stress")):
            manifest = pd.read_csv(root / scope / "manifest.csv")
            for _, row in manifest.iterrows():
                path = RESULT.query_sql_path(pd.Series({
                    "query": row["query_id"], "sql_path": row["path"], "workload_category": category,
                }))
                self.assertEqual(path, root / scope / row["path"])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["content_sha256"])
                checked += 1
        self.assertEqual(checked, 932)

    def test_star_expands_schema_without_double_counting_join_and_filter_columns(self):
        columns = RESULT.participating_columns(
            "SELECT * FROM (ta a LEFT JOIN tb b ON a.id=b.id) WHERE b.flag>0", self.schema)
        self.assertEqual(columns, ["a.id", "a.value", "b.flag", "b.id"])
        self.assertEqual(RESULT.participating_columns(
            "SELECT a.*, a.value FROM ta a JOIN ta other ON a.id=other.id", self.schema),
            ["a.id", "a.value", "other.id"])

    def test_quoted_columns_literals_comments_and_repeated_references(self):
        sql = '''SELECT "A"."value" AS output, a.value + b.flag,
                 'a.fake, ignored.name' AS message FROM ta "A" JOIN tb b ON a.id=b.id
                 WHERE b.flag > 0 /* b.fake */ -- a.another_fake
                 ORDER BY output'''
        self.assertEqual(RESULT.participating_columns(sql, self.schema),
                         ["a.id", "a.value", "b.flag", "b.id"])

    def test_count_star_is_not_a_projection_wildcard(self):
        self.assertEqual(RESULT.participating_columns(
            "SELECT COUNT(*) AS n FROM ta a JOIN tb b ON a.id=b.id WHERE b.flag=1", self.schema),
            ["a.id", "b.flag", "b.id"])
        self.assertEqual(RESULT.participating_columns(
            "SELECT a.id, SUM(a.value * 2) AS total FROM ta a GROUP BY a.id HAVING SUM(a.value)>0",
            self.schema), ["a.id", "a.value"])

    def test_graph_input_filter_scan_attributes_preserve_dependencies(self):
        schema = {name: ["src", "dst"] for name in ("r1", "r2", "r3")}
        sql = ("SELECT COUNT(*) FROM R1 LEFT JOIN "
               "(SELECT src, dst FROM R2 WHERE src <= 40) R2 ON R1.dst=R2.src "
               "RIGHT JOIN (SELECT src, dst FROM R3 WHERE src <= 40) R3 ON R2.dst=R3.src")
        self.assertEqual(RESULT.participating_columns(sql, schema),
                         ["r1.dst", "r2.dst", "r2.src", "r3.dst", "r3.src"])
        self.assertEqual(len(RESULT.participating_columns(sql.replace("COUNT(*)", "*"), schema)), 6)
        for modified in (sql.replace("src <= 40", "dst >= 40"),
                         sql.replace("src, dst", "src AS dst, dst AS src"),
                         sql.replace(") R2", ") other")):
            with self.subTest(sql=modified), self.assertRaises(ValueError):
                RESULT.participating_columns(modified, schema)
        with self.assertRaises(ValueError):
            RESULT.participating_columns(sql, dict(schema, r2=["src", "dst", "weight"]))

    def test_unqualified_columns_resolve_uniquely_and_unsupported_scopes_fail(self):
        self.assertEqual(RESULT.participating_columns(
            "SELECT value FROM ta a JOIN tb b ON a.id=b.id", self.schema),
            ["a.id", "a.value", "b.id"])
        for sql in ("SELECT id FROM ta a JOIN tb b ON a.id=b.id",
                    "SELECT a.missing FROM ta a", "SELECT * FROM (SELECT * FROM ta) t",
                    "SELECT * FROM ta JOIN tb USING (id)"):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                RESULT.participating_columns(sql, self.schema)

    def test_sql_version_paths_and_catalog_reuse_are_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for scope, projection in (("benchmark", "*"), ("v2/benchmark", "a.id")):
                path = root / "outerjoin_benchmark" / scope / "graph/query.sql"
                path.parent.mkdir(parents=True)
                path.write_text(f"SELECT {projection} FROM ta a")
            catalog = {"database": "fixture", "tables": self.schema}
            with mock.patch.object(RESULT, "SCRIPT_DIR", root), \
                    mock.patch.object(RESULT, "database_columns", return_value=catalog) as read:
                cache = {}
                first = RESULT.query_attributes(pd.Series({"query": "query", "family": "graph",
                    "sql_path": "graph/query.sql", "workload_category": "v1"}), cache)
                second = RESULT.query_attributes(pd.Series({"query": "query", "family": "graph",
                    "sql_path": "graph/query.sql", "workload_category": "v2"}), cache)
            self.assertEqual(read.call_count, 1)
            self.assertEqual((first["attribute_count"], second["attribute_count"]), (2, 1))
            self.assertNotEqual(first["attribute_sql_sha256"], second["attribute_sql_sha256"])


class UnifiedResultEntryTest(unittest.TestCase):
    def setUp(self):
        install_sql_metadata_fixture(self)

    def test_default_date_directory_and_thread_isolation(self):
        frame = pd.DataFrame({"run": ["20260926_t32", "20260926_t32"]})
        self.assertEqual(RESULT.result_directories(frame),
                         {"20260926_t32": RESULT.SCRIPT_DIR / "results/plots/20260926"})
        frame = pd.DataFrame({"run": ["20260926_t16", "20260926_t32", "20260928_t32"]})
        output = RESULT.result_directories(frame)
        self.assertEqual(output["20260926_t16"], RESULT.DEFAULT_OUTPUT_ROOT / "20260926/t16")
        self.assertEqual(output["20260926_t32"], RESULT.DEFAULT_OUTPUT_ROOT / "20260926/t32")
        self.assertEqual(output["20260928_t32"], RESULT.DEFAULT_OUTPUT_ROOT / "20260928")
        override = Path(tempfile.gettempdir()) / "outeryan-custom-output"
        self.assertEqual(RESULT.result_directories(frame, override)["20260926_t16"],
                         override.resolve() / "20260926_t16")
        self.assertEqual(RESULT.result_directories(frame.iloc[-1:], override)["20260928_t32"],
                         override.resolve())

    def test_batch_groups_keep_distinct_output_directories(self):
        runs = ["20260926_110332_t32", "20260926_163933_t32"]
        frame = pd.DataFrame({"run": runs})
        output = RESULT.result_directories(frame, group_by="run")
        self.assertEqual(len(set(output.values())), 2)
        for run in runs:
            self.assertEqual(output[run], RESULT.DEFAULT_OUTPUT_ROOT / "20260926" / run)

    def test_date_only_generates_figures_statistics_and_metadata_without_latex(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            results.mkdir()
            source = results / "experiment_onoff_benchmark_20260926_110332_t32_v1.csv"
            frame = ReportMetadataTest.frame().iloc[:2].copy()
            frame["profile_threads"] = 32
            frame["profile_total_time_s"] = frame["profile_cpu_time_s"]
            for _, seconds, ratio, _ in RESULT.PHASES:
                frame[ratio] = frame[seconds] / frame["profile_cpu_time_s"]
            frame.to_csv(source, index=False)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            with mock.patch.object(RESULT, "SCRIPT_DIR", root), \
                    mock.patch.object(RESULT, "DEFAULT_OUTPUT_ROOT", results / "plots"):
                self.assertEqual(RESULT.main(["--date", "2026-09-26"]), 0)
            output = results / "plots/20260926"
            for filename in ("overview.pdf", "speedup_all_queries.pdf", "speedup_all_queries.png",
                             "phase_breakdown_outeryan.pdf", "report_metadata.json",
                             "STATISTICS.md", "statistics.json", "plot_selection.json"):
                self.assertGreater((output / filename).stat().st_size, 0, filename)
            self.assertFalse(list(output.glob("*.tex")))
            report = json.loads((output / "statistics.json").read_text())
            self.assertEqual(report["unique_queries"], 2)
            self.assertEqual(report["groups"][0]["counts"]["measured"], 2)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            self.assertFalse((results / "plots/20260926_t32").exists())

    def test_statistics_only_does_not_import_matplotlib(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocked = root / "matplotlib"
            blocked.mkdir()
            (blocked / "__init__.py").write_text("raise RuntimeError('Matplotlib must not be loaded')\n")
            source = root / "input.csv"
            ReportMetadataTest.frame().iloc[:2].to_csv(source, index=False)
            output = root / "statistics"
            env = dict(os.environ, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run([
                sys.executable, str(Path(RESULT.__file__).resolve()), "--statistics-only",
                "--run", "20260926_110332", "--output-dir", str(output), str(source),
            ], cwd=root, env=env, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads((output / "statistics.json").read_text())["unique_queries"], 2)
            self.assertFalse((output / "overview.pdf").exists())

    def test_include_subsecond_cli_changes_all_outputs_and_restores_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "experiment_onoff_benchmark_20261002_213551_t32.csv"
            frame = ReportMetadataTest.frame().iloc[[3]].copy()
            frame["profile_threads"] = 32
            frame["profile_total_time_s"] = frame["profile_cpu_time_s"]
            for _, seconds, ratio, _ in RESULT.PHASES:
                frame[ratio] = frame[seconds] / frame["profile_cpu_time_s"]
            frame.to_csv(source, index=False)
            output = root / "review"
            self.assertEqual(RESULT.main([str(source), "--output-dir", str(output),
                                          "--include-subsecond"]), 0)
            report = json.loads((output / "statistics.json").read_text())
            paper = json.loads((output / "report_metadata.json").read_text())
            phases = json.loads((output / "phase_queries.json").read_text())
            self.assertEqual(report["valid_queries"], 1)
            self.assertEqual(report["method"]["minimum_runtime_seconds"], 0)
            self.assertEqual(len(report["phase_profiles"]["queries"]), 1)
            self.assertEqual(paper["corpus"]["total"], 1)
            self.assertEqual(len(phases["queries"]), 1)
            self.assertIn("No minimum runtime filter", phases["runtime_filter"])
            self.assertFalse(list(output.glob("*.tex")))
            self.assertEqual(RESULT.MIN_RUNTIME_SECONDS, 1)
            self.assertEqual(RESULT.build_statistics(frame)["valid_queries"], 0)

    def test_invalid_date_and_sample_counts_fail_before_loading(self):
        with mock.patch.object(RESULT, "load") as loader:
            for args in (["--date", "20260230"], ["--date", "oops"],
                         ["--phase-samples-per-benchmark", "0"], ["--representatives-per-benchmark", "-1"]):
                with self.subTest(args=args), self.assertRaises(SystemExit) as error:
                    RESULT.main(args)
                self.assertEqual(error.exception.code, 2)
            loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
