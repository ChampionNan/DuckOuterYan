"""Safety checks for the current-manifest, numeric-only paper refresh."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import refresh_paper_results as refresh


class CurrentManifestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.sql = self.root / "one.sql"
        self.sql.write_text("SELECT 1;\n")
        self.sha = hashlib.sha256(self.sql.read_bytes()).hexdigest()
        self.manifest = self.root / "manifest.csv"
        pd.DataFrame([{"query_id": "one", "path": "one.sql", "content_sha256": self.sha}]).to_csv(
            self.manifest, index=False)

    def observation(self, **changes):
        row = {"query": "one", "family": "TPC-DS", "sql_content_sha256": self.sha,
               "sql_identity": "tpcds:one", "source_run": "20261002", "source_csv": "old.csv",
               "timing_threads": 32, "execution_host": "cpu9", "database_signature": "same-db",
               "timing_protocol": "warm-profile-then-timing-v1", "timing_samples": 1,
               "timing_estimator": "single_post_warmup", "timing_status": "measured"}
        return {**row, **changes}

    def load(self, rows):
        with patch.object(refresh.plot, "load", return_value=pd.DataFrame(rows)):
            return refresh.current_observations(["unused.csv"], self.manifest)

    def test_exact_sql_only_and_retired_exclusion(self):
        _, rows, excluded, pending = self.load([
            self.observation(), self.observation(query="retired", sql_identity="retired"),
            self.observation(sql_content_sha256="changed", source_run="20261003")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(excluded.refresh_exclusion), {"retired_or_not_active", "changed_sql_hash"})
        self.assertTrue(pending.empty)

    def test_latest_failure_replaces_success(self):
        _, rows, _, _ = self.load([
            self.observation(), self.observation(source_run="20261005", timing_status="timeout")])
        self.assertEqual(rows.iloc[0].timing_status, "timeout")

    def test_changed_sql_is_not_reused(self):
        with self.assertRaisesRegex(ValueError, "No exact active-SQL"):
            self.load([self.observation(sql_content_sha256="not-current")])

    def test_manifest_hash_is_checked(self):
        self.sql.write_text("SELECT 2;\n")
        with self.assertRaisesRegex(ValueError, "does not match its manifest"):
            self.load([self.observation()])

    def test_no_cross_host_pooling(self):
        second = self.root / "two.sql"
        second.write_text("SELECT 2;\n")
        second_sha = refresh.digest(second)
        pd.DataFrame([
            {"query_id": "one", "path": "one.sql", "content_sha256": self.sha},
            {"query_id": "two", "path": "two.sql", "content_sha256": second_sha},
        ]).to_csv(self.manifest, index=False)
        with self.assertRaisesRegex(ValueError, "Incompatible execution_host"):
            self.load([self.observation(), self.observation(
                query="two", sql_identity="tpcds:two", sql_content_sha256=second_sha,
                execution_host="cpu8")])

    def test_complete_family_replacement_does_not_carry_forward_old_success(self):
        source = (self.root / "new.csv").resolve()
        rows = [self.observation(), self.observation(
            query="no-longer-active", sql_identity="retired", source_csv=str(source), source_run="20261005")]
        # New batch is a complete replacement, not an invitation to reuse old success.
        with patch.object(refresh.plot, "load", return_value=pd.DataFrame(rows)):
            with self.assertRaisesRegex(ValueError, "No exact active-SQL"):
                refresh.current_observations(["old.csv", str(source)], self.manifest, source)

    def test_graph_aggregation_is_a_supplementary_control(self):
        pd.DataFrame([{"query_id": "one", "path": "one.sql", "content_sha256": self.sha,
                       "provenance_class": "synthetic_graph"}]).to_csv(self.manifest, index=False)
        _, rows, _, _ = self.load([self.observation(workload_component="structural")])
        self.assertEqual(rows.iloc[0].workload_component, "evaluation")

    def test_historical_derived_pattern_is_structural(self):
        pd.DataFrame([{"query_id": "one", "path": "one.sql", "content_sha256": self.sha,
                       "provenance_class": "historical_pattern_adaptation"}]).to_csv(self.manifest, index=False)
        _, rows, _, _ = self.load([self.observation(workload_component="historical_recovery")])
        self.assertEqual(rows.iloc[0].workload_component, "structural")


class PolicyTableTests(unittest.TestCase):
    def test_figure_captions_disclose_screen_and_defaults(self):
        tex = refresh.figure_includes_tex(235, 0.5)
        self.assertIn(r"\fix{235}", tex)
        self.assertIn(r"\fix{$0.5000\times$}", tex)
        self.assertIn("policy defaults are not plotted", tex)
        self.assertEqual(tex.count(r"\begin{figure*}"), 2)

    def test_reporting_composition_counts_only_its_input_cohort(self):
        rows = pd.DataFrame([
            {"query": "derived", "family": "TPC-DS", "workload_component": "structural",
             "provenance_class": "historical_pattern_adaptation"},
            {"query": "control", "family": "graph", "workload_component": "evaluation",
             "provenance_class": "synthetic_graph"},
        ])
        source = refresh.benchmark_composition(rows, "before screening")
        reported = refresh.benchmark_composition(rows.iloc[1:], "after screening")
        self.assertEqual(source["total"], 2)
        self.assertEqual(reported["total"], 1)
        self.assertEqual(reported["structural"], 0)
        self.assertEqual(reported["supplementary"], 1)
        self.assertEqual(reported["population"], "after screening")

    def test_reviewed_case_analysis_replaces_only_placeholder(self):
        section = r"\subsubsection{Case Query Analysis}"
        fragment = "unchanged\n" + section + "\n\n" + r"\fix{TODO}" + "\nfollowing"
        case = section + "\n\nVerified case."
        self.assertEqual(refresh.replace_case_analysis(fragment, case),
                         "unchanged\n" + case + "\nfollowing")
        with self.assertRaisesRegex(ValueError, "must start"):
            refresh.replace_case_analysis(fragment, "Missing heading")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            refresh.replace_case_analysis("No placeholder", case)

    def test_defaults_change_distribution_but_never_runtime_sum(self):
        rows = pd.DataFrame([
            {"family": "TPC-DS", "selected_plan": "OUTERYAN", "correct": "TRUE", "note": "OK",
             "timing_status": "measured", "tm_off": 8.0, "tm_on": 2.0},
            {"family": "TPC-DS", "selected_plan": "OUTERYAN", "correct": "TRUE", "note": "FALLBACK-SKIP",
             "timing_status": "fallback-skip", "tm_off": float("nan"), "tm_on": float("nan")},
            {"family": "TPC-DS", "selected_plan": "DUCKDB", "correct": "TIMEOUT", "note": "TIMEOUT",
             "timing_status": "timeout", "tm_off": float("nan"), "tm_on": float("nan")},
        ])
        with patch.object(refresh.plot, "prepare_queries", return_value=pd.DataFrame({"valid_timing": [True, False, False]})):
            table = refresh.policy_statistics(rows)
        selected = next(row for row in table if row["subset"] == "outeryan_selected" and row["family"] == "All")
        self.assertEqual(selected["n"], 2)
        self.assertEqual(selected["measured"], 1)
        self.assertEqual(selected["policy_defaults"], 1)
        self.assertAlmostEqual(selected["geomean"], 2.0)
        self.assertEqual(selected["total_ratio"], 4.0)
        tex = refresh.runtime_table_tex(table)
        self.assertIn(r"\caption{Statistics across benchmark workloads}", tex)
        self.assertIn("defaults are not measured speed-ups", tex)
        self.assertNotIn("excluding measured pairs with both runtimes below", tex)


if __name__ == "__main__":
    unittest.main()
