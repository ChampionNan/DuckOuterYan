"""Statistics, figures and the single table bundle describe one population."""
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import publish_plan_cohort as publish
import report_plan_cohort as report
import verify_benchmark_reproduction as reproduce
from test_gen_outerjoin_benchmark import forbid_result_access

TABLE_OUTPUTS = {
    "current_results.csv", "plan_cohort_statistics.csv", "phase_summary.csv",
    "benchmark_composition.csv", "benchmark_dimensions.csv", "shape_statistics.csv",
    "optimization_representatives.csv", "report_metadata.json", "tables.tex",
}
FIGURE_OUTPUTS = {
    stem + suffix for stem in ("speedup_all_queries", "phase_breakdown_outeryan")
    for suffix in (".pdf", ".png")
}


class CohortPublicationTest(unittest.TestCase):
    def test_snapshot_ignores_only_finder_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".DS_Store").write_bytes(b"Finder metadata")
            (root / "query.sql").write_text("SELECT 1;\n")
            (root / ".unexpected").write_text("Still verify this file.\n")
            self.assertEqual(set(reproduce.snapshot(root)), {"query.sql", ".unexpected"})

    def test_generation_is_result_free_and_byte_identical(self):
        with forbid_result_access():
            result = reproduce.verify()
        self.assertEqual(result["query_count"], 321)
        self.assertTrue(result["byte_identical"])

    def test_current_publication(self):
        if not all((report.ROOT / r["path"]).exists() for r in
                   report.cohort.policy()["source_files"] + report.cohort.query_updates.source_files()):
            self.skipTest("Pinned historical measurements are optional local artifacts")
        with tempfile.TemporaryDirectory() as temporary, patch.object(
                publish.plot, "query_attributes", side_effect=FileNotFoundError("No catalog in unit test")):
            out = Path(temporary)
            (out / "existing_manuscript.tex").write_text("Keep this manuscript unchanged.\n")
            result = publish.publish(out, figures=False)
            self.assertEqual(result["figure_points"], dict(runtime_pairs=282, ratio_points=321))
            self.assertEqual(result["phase_profiles"], 282)
            self.assertEqual(result["phase_duckdb_timeout_profiles"], 4)
            details = report.b.read_manifest(out / "current_results.csv")
            samples = sorted((row for row in details if row["phase_figure_order"]),
                             key=lambda row: float(row["phase_figure_order"]))
            self.assertEqual([row["short_query"] for row in samples], [
                "G-G-LD-06", "G-G-RD-06", "A-H-LD-10", "Q-H-LD-24",
                "A-D-LD-05", "A-D-RD-06", "Q-J-LD-24", "A-J-RD-08",
            ])
            self.assertEqual(sum(r["n"] for r in result["workload"][:-1]), 321)
            ids = result["optimization_representatives"]
            self.assertEqual((len(ids["main"]), len(ids["appendix"])), (3, 9))
            self.assertFalse(set(ids["main"]) & set(ids["appendix"]))
            self.assertEqual({p.name for p in out.glob("*.tex")}, {"existing_manuscript.tex", "tables.tex"})
            tex = (out / "tables.tex").read_text()
            self.assertEqual(tex.count(r"\begin{table*}"), 6)
            self.assertNotIn(r"\paragraph", tex)
            self.assertIn(r"\# Attributes", tex)
            self.assertIn("600 s proxy", tex)
            self.assertEqual((out / "existing_manuscript.tex").read_text(), "Keep this manuscript unchanged.\n")
            self.assertFalse((out / "PAPER_UPDATE_CHECKLIST.txt").exists())
            self.assertEqual({p.name for p in out.iterdir()}, TABLE_OUTPUTS | {"existing_manuscript.tex"})
            for r in report.b.read_manifest(out / "phase_summary.csv"):
                self.assertAlmostEqual(sum(float(r[k + "_pct"]) for k in publish.PHASE_KEYS), 100)
            details = report.b.read_manifest(out / "current_results.csv")
            self.assertEqual(len(details), 321)
            self.assertEqual(sum(r["phase_summary_included"] == "True" for r in details), 282)
            reps = report.b.read_manifest(out / "optimization_representatives.csv")
            self.assertEqual(sum(r["table_group"] == "main" for r in reps), 3)
            for r in details:
                if r["speedup_source"] == "duckdb_timeout_600s":
                    self.assertEqual(r["duckdb_status"], "timeout")
                    self.assertEqual(float(r["effective_duckdb_s"]), 600)
                    self.assertFalse(r["tm_off"])
            self.assertTrue((out / "shape_statistics.csv").is_file())

    def test_latex_option_is_not_supported(self):
        with self.assertRaises(SystemExit) as error:
            publish.main(["--latex"])
        self.assertEqual(error.exception.code, 2)

    def test_phase_samples_keep_display_order_not_selection_order(self):
        frame = publish.plot.pd.DataFrame([
            dict(query=f"{family}_{suffix}", family=family, topology=shape, short_query=suffix)
            for family in reversed(publish.plot.FAMILY_ORDER)
            for shape, suffix in [("bushy", "B-01"), ("right-deep", "RD-01"),
                                  ("left-deep", "LD-02"), ("left-deep", "LD-01")]
        ])
        with patch.object(publish.plot, "diverse_phase_samples", return_value=frame) as select:
            result = publish.phase_figure_samples(frame)
        select.assert_called_once_with(frame, 4, .5)
        self.assertEqual(result["query"].tolist(), [
            f"{family}_{suffix}" for family in publish.plot.FAMILY_ORDER for suffix in ("LD-01", "LD-02")
        ])

    def test_default_validation_never_generates(self):
        with patch.object(reproduce.benchmark, "validate", return_value=[{}] * 321), \
             patch.object(reproduce, "verify") as verify:
            reproduce.main(["--validate-only"])
            verify.assert_not_called()

    def test_phase_substitutions_preserve_other_rows_and_require_measured_speedup(self):
        original_id, replacement_id = next(iter(publish.PHASE_REPLACEMENTS.items()))

        def row(query, off=3., on=2.):
            return dict(query=query, short_query=query, family="graph", topology="left-deep",
                        selected_plan="OUTERYAN", correct="TRUE", profile_status="OK",
                        speedup_source="measured", tm_off=off, tm_on=on, profile_threads=32,
                        timing_threads=32, profile_total_time_s=10., profile_cpu_time_s=10.,
                        profile_wall_time_s=2., profile_round1_operator_s=1.,
                        profile_round2_operator_s=2., profile_round3_operator_s=3.,
                        profile_other_elapsed_s=4., profile_round1_ratio=.1,
                        profile_round2_ratio=.2, profile_round3_ratio=.3, profile_other_ratio=.4)

        samples = publish.plot.pd.DataFrame([row("unchanged"), row(original_id)])
        for changes, expected in [({}, replacement_id), ({"tm_on": .1}, original_id),
                                  ({"tm_on": 4.}, original_id),
                                  ({"speedup_source": "duckdb_timeout_600s"}, original_id),
                                  ({"profile_status": "ERROR"}, original_id)]:
            candidate = row(replacement_id)
            candidate.update(changes)
            frame = publish.plot.pd.DataFrame([candidate])
            result = publish.replace_short_phase_representatives(frame, samples)
            self.assertEqual(result["query"].tolist(), ["unchanged", expected])
            self.assertEqual(result.iloc[0].tm_on, samples.iloc[0].tm_on)
        result = publish.replace_short_phase_representatives(samples, samples)
        self.assertEqual(result["query"].tolist(), samples["query"].tolist())

    def test_plot_markers_and_panel_spacing(self):
        publish.plot._load_plotting()
        from matplotlib.collections import PathCollection
        frame = publish.plot.pd.DataFrame([
            dict(query=f"q{i}", family="graph", speedup=speedup, speedup_source=source,
                 effective_duckdb_s=off, effective_outeryan_s=on)
            for i, (source, speedup, off, on) in enumerate([
                ("measured", .8, .8, 1.), ("measured", 1.2, 1.2, 1.),
                ("fallback_default_1x", 1., None, None), ("duckdb_timeout_600s", 20000., 600., .03)])])
        with patch.object(publish.plot, "save_page") as save:
            publish.runtime_plot(None, frame)
        figure = save.call_args.args[1]
        try:
            self.assertAlmostEqual(figure.subplotpars.wspace, .13)
            self.assertAlmostEqual(figure.subplotpars.top, .90)
            publish.plot.np.testing.assert_allclose(figure.get_size_inches(), [10.7, 3.25])
            left, right = figure.axes[:2]
            self.assertEqual(left.get_aspect(), "auto")
            self.assertEqual(left.get_xlim(), left.get_ylim())
            self.assertAlmostEqual(left.get_position().width,
                                   left.get_subplotspec().get_position(figure).width)
            self.assertAlmostEqual(left.get_position().height, right.get_position().height)
            original = right.get_subplotspec().get_position(figure)
            self.assertAlmostEqual(right.get_position().x0, original.x0 - .0035)
            self.assertAlmostEqual(right.get_position().width, original.width)
            self.assertAlmostEqual(right.get_position().height, original.height)
            self.assertEqual([title.get_fontsize() for title in figure.texts], [9.2, 9.2])
            self.assertEqual(figure.texts[0].get_position()[1], figure.texts[1].get_position()[1])
            self.assertEqual(left.xaxis.label.get_fontsize(), 10)
            self.assertEqual(right.get_yticklabels()[0].get_fontsize(), 9)
            figure.canvas.draw()
            renderer = figure.canvas.get_renderer()
            ticks = [.8, 1, 2, 3, 4, 5, 10, 100, 1000, 10000]
            publish.plot.np.testing.assert_allclose(right.get_xticks(), publish.plot.np.log10(ticks))
            self.assertEqual([label.get_text() for label in right.get_xticklabels()],
                             [f"{value:g}" for value in ticks])
            tick_boxes = [label.get_window_extent(renderer) for label in right.get_xticklabels()]
            for first, second in zip(tick_boxes, tick_boxes[1:]):
                self.assertGreater(second.x0 - first.x1, 2 * figure.dpi / 72)
            label_left = min(label.get_window_extent(renderer).x0 for label in right.get_yticklabels())
            self.assertGreater(label_left - left.get_window_extent(renderer).x1, 2 * figure.dpi / 72)
            self.assertEqual(len(figure.legends), 1)
            legend = figure.legends[0]
            self.assertEqual(len(legend.get_texts()), 7)
            self.assertEqual([text.get_text() for text in legend.get_texts()][4:6],
                             ["Measured, faster/equal", "Measured, slower"])
            legend_rows = [text.get_window_extent(renderer).y0 for text in legend.get_texts()]
            self.assertAlmostEqual(max(legend_rows), min(legend_rows))
            legend_box = legend.get_window_extent(renderer)
            self.assertGreater(legend_box.y0, max(axis.get_window_extent(renderer).y1 for axis in (left, right)))
            self.assertGreaterEqual(legend_box.x0, 0)
            self.assertLessEqual(legend_box.x1, figure.bbox.width)
            for axis, title in zip((left, right), figure.texts):
                self.assertGreaterEqual(axis.xaxis.label.get_window_extent(renderer).y0
                                        - title.get_window_extent(renderer).y1, 2.4 * figure.dpi / 72)
            points = [c for c in figure.axes[1].collections if isinstance(c, PathCollection)]
            measured, timeout, fallback = points[:3]
            publish.plot.np.testing.assert_array_equal(measured.get_paths()[0].vertices,
                                                      fallback.get_paths()[0].vertices)
            self.assertEqual(measured.get_alpha(), fallback.get_alpha())
            self.assertNotEqual(len(timeout.get_paths()[0].vertices), len(measured.get_paths()[0].vertices))
        finally:
            publish.plot.plt.close(figure)

    def test_fresh_run_never_reads_historical_csvs(self):
        if not all((report.ROOT / r["path"]).exists() for r in
                   report.cohort.policy()["source_files"] + report.cohort.query_updates.source_files()):
            self.skipTest("Pinned historical measurements are optional local artifacts")
        _, _, records, _ = report.load_observations()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fresh.csv"
            report.b.write_csv(path, records)
            spec = report.cohort.policy()
            spec["source_files"] = [dict(path="missing-historical.csv", sha256="invalid")]
            with patch.object(report.cohort, "policy", return_value=spec):
                details, retired, _, summary = report.build([path])
            self.assertEqual(len(details), 321)
            self.assertEqual(retired, [])
            self.assertEqual(summary["measurement_mode"], "new_run")
            updated = report.cohort.query_updates.policy()["replacements"][0]
            record = next(row for row in records if row["query"] == updated["query_id"])
            record["sql_content_sha256"] = updated["original_sha256"]
            report.b.write_csv(path, records)
            with self.assertRaisesRegex(ValueError, "SQL hash mismatch"):
                report.build([path])
            record["sql_content_sha256"] = updated["content_sha256"]
            records.pop()
            report.b.write_csv(path, records)
            with self.assertRaisesRegex(ValueError, "cover exactly"):
                report.build([path])

    def test_actual_fallback_does_not_depend_on_historical_role(self):
        from test_report_plan_cohort import ReportPlanCohortTest
        fixture = ReportPlanCohortTest()
        raw = fixture.raw(selected_plan="DUCKDB", timing_status="fallback-skip",
                          duckdb_status="fallback-skip", outeryan_status="fallback-skip")
        record = report.observation(fixture.member("selected"), raw)
        self.assertEqual(record["speedup"], 1)
        self.assertIsNone(record["effective_duckdb_s"])

    def test_cold_checkout_can_publish_new_results_without_history(self):
        # Synthetic fixtures exercise reporting only, never published measurements.
        rows = []
        for index, meta in enumerate(report.b.validate(report.b.ROOT / "benchmark")):
            rows.append(dict(query=meta["query_id"], sql_content_sha256=meta["content_sha256"],
                selected_plan="OUTERYAN", correct="NOT-CHECKED", timing_status="measured",
                duckdb_status="measured", outeryan_status="measured", tm_off=str(2 + index / 100),
                tm_on="1", optimizer_profile_status="not-run", profile_status="not-run",
                duckdb_timeout_seconds="600", timing_samples="5", timing_threads="32"))
        spec = report.cohort.policy()
        spec["source_files"] = [dict(path="unavailable-history.csv", sha256="invalid")]
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "synthetic-test-only.csv"
            report.b.write_csv(source, rows)
            with patch.object(report.cohort, "policy", return_value=spec):
                result = publish.publish(Path(temp) / "report", [source], figures=True)
            self.assertEqual(result["benchmark_queries"], 321)
            self.assertEqual(result["measurement_mode"], "new_run")
            self.assertEqual(result["phase_profiles"], 0)
            self.assertEqual(result["figure_points"]["ratio_points"], 321)
            self.assertTrue((Path(temp) / "report/speedup_all_queries.pdf").is_file())
            self.assertEqual([p.name for p in (Path(temp) / "report").glob("*.tex")], ["tables.tex"])
            self.assertEqual({p.name for p in (Path(temp) / "report").iterdir()},
                             TABLE_OUTPUTS | FIGURE_OUTPUTS)


if __name__ == "__main__":
    unittest.main()
