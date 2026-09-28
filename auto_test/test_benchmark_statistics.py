import json
import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from auto_test import benchmark_statistics as STATS


class BenchmarkStatisticsTest(unittest.TestCase):
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

    def test_fallback_skip_contributes_default_speedup_without_runtime(self):
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
        self.assertEqual(summary["counts"]["valid"], 2)
        self.assertEqual(summary["counts"]["measured"], 1)
        self.assertEqual(summary["counts"]["fallback_skips"], 1)
        self.assertEqual(summary["counts"]["equal"], 1)
        self.assertEqual(summary["totals"]["off_s"], measured["tm_off"])
        self.assertEqual(summary["totals"]["on_s"], measured["tm_on"])
        fallback_row = next(row for row in report["queries"] if row["query"] == "fallback")
        self.assertEqual(fallback_row["speedup"], 1.0)
        self.assertEqual(fallback_row["speedup_source"], "fallback-default")
        self.assertFalse(fallback_row["valid_timing"])
        self.assertTrue(fallback_row["valid_speedup"])

    def test_correctness_timeout_status_is_excluded_as_timeout(self):
        good = self.frame().iloc[0].to_dict()
        frame = pd.DataFrame([
            good,
            dict(good, query="timeout", correct="TIMEOUT", note="TIMEOUT", tm_on=None),
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


if __name__ == "__main__":
    unittest.main()
