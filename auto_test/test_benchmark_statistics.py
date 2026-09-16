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
            for text in ("Geomean", "Percentiles", "OFF/ON runtime", "Shape breakdown", "Extreme queries", "Sources"):
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


if __name__ == "__main__":
    unittest.main()
