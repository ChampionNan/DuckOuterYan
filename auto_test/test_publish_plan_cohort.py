"""Statistics and figures must describe one population without authoring LaTeX."""
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


class CohortPublicationTest(unittest.TestCase):
    def test_generation_is_result_free_and_byte_identical(self):
        with forbid_result_access():
            result = reproduce.verify()
        self.assertEqual(result["query_count"], 350)
        self.assertTrue(result["byte_identical"])

    def test_current_publication(self):
        if not all((report.ROOT / r["path"]).exists() for r in report.cohort.policy()["source_files"]):
            self.skipTest("Pinned historical measurements are optional local artifacts")
        with tempfile.TemporaryDirectory() as temporary, patch.object(
                publish.plot, "query_attributes", side_effect=FileNotFoundError("No catalog in unit test")):
            out = Path(temporary)
            (out / "existing_manuscript.tex").write_text("Keep this manuscript unchanged.\n")
            result = publish.publish(out, figures=False)
            self.assertEqual(result["figure_points"], dict(runtime_pairs=285, ratio_points=350))
            self.assertEqual(result["phase_profiles"], 281)
            self.assertEqual(sum(r["n"] for r in result["workload"][:-1]), 350)
            ids = result["optimization_representatives"]
            self.assertEqual((len(ids["main"]), len(ids["appendix"])), (3, 9))
            self.assertFalse(set(ids["main"]) & set(ids["appendix"]))
            self.assertEqual([p.name for p in out.glob("*.tex")], ["existing_manuscript.tex"])
            self.assertEqual((out / "existing_manuscript.tex").read_text(), "Keep this manuscript unchanged.\n")
            self.assertFalse((out / "PAPER_UPDATE_CHECKLIST.txt").exists())
            for r in report.b.read_manifest(out / "phase_summary.csv"):
                self.assertAlmostEqual(sum(float(r[k + "_pct"]) for k in publish.PHASE_KEYS), 100)
            details = report.b.read_manifest(out / "current_results.csv")
            self.assertEqual(len(details), 350)
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

    def test_default_validation_never_generates(self):
        with patch.object(reproduce.benchmark, "validate", return_value=[{}] * 350), \
             patch.object(reproduce, "verify") as verify:
            reproduce.main(["--validate-only"])
            verify.assert_not_called()

    def test_plot_markers_and_panel_spacing(self):
        publish.plot._load_plotting()
        from matplotlib.collections import PathCollection
        frame = publish.plot.pd.DataFrame([
            dict(query=f"q{i}", family="graph", speedup=speedup, speedup_source=source,
                 effective_duckdb_s=off, effective_outeryan_s=on)
            for i, (source, speedup, off, on) in enumerate([
                ("measured", .8, .8, 1.), ("measured", 1.2, 1.2, 1.),
                ("fallback_default_1x", 1., None, None), ("duckdb_timeout_600s", 600., 600., 1.)])])
        with patch.object(publish.plot, "save_page") as save:
            publish.runtime_plot(None, frame)
        figure = save.call_args.args[1]
        try:
            self.assertAlmostEqual(figure.subplotpars.wspace, .13)
            self.assertAlmostEqual(figure.subplotpars.top, .86)
            points = [c for c in figure.axes[1].collections if isinstance(c, PathCollection)]
            measured, timeout, fallback = points[:3]
            publish.plot.np.testing.assert_array_equal(measured.get_paths()[0].vertices,
                                                      fallback.get_paths()[0].vertices)
            self.assertEqual(measured.get_alpha(), fallback.get_alpha())
            self.assertNotEqual(len(timeout.get_paths()[0].vertices), len(measured.get_paths()[0].vertices))
        finally:
            publish.plot.plt.close(figure)

    def test_fresh_run_never_reads_historical_csvs(self):
        if not all((report.ROOT / r["path"]).exists() for r in report.cohort.policy()["source_files"]):
            self.skipTest("Pinned historical measurements are optional local artifacts")
        _, _, records, _ = report.load_observations()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fresh.csv"
            report.b.write_csv(path, records)
            spec = report.cohort.policy()
            spec["source_files"] = [dict(path="missing-historical.csv", sha256="invalid")]
            with patch.object(report.cohort, "policy", return_value=spec):
                details, retired, _, summary = report.build([path])
            self.assertEqual(len(details), 350)
            self.assertEqual(retired, [])
            self.assertEqual(summary["measurement_mode"], "new_run")
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


if __name__ == "__main__":
    unittest.main()
