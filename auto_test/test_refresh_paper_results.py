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

    def test_replacement_audit_does_not_reuse_old_time_after_failure(self):
        old = self.observation(tm_off=8.0, tm_on=2.0, correct="TRUE", selected_plan="OUTERYAN")
        new = self.observation(tm_off=float("nan"), tm_on=float("nan"), correct="TIMEOUT",
                               selected_plan="OUTERYAN", source_run="20261007", timing_status="timeout")
        _, rows, rejected, _ = self.load([old, new])
        audit = refresh.replacement_audit(rows, rejected)
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit.iloc[0].speedup_old, 4.0)
        self.assertTrue(pd.isna(audit.iloc[0].speedup_new))
        self.assertEqual(audit.iloc[0].timing_status_new, "timeout")

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

    def test_full_family_replacement_retains_later_partial_failure(self):
        source = (self.root / "new.csv").resolve()
        later = (self.root / "partial.csv").resolve()
        second = self.root / "two.sql"
        second.write_text("SELECT 2;\n")
        sha = refresh.digest(second)
        pd.DataFrame([
            {"query_id": "one", "path": "one.sql", "content_sha256": self.sha},
            {"query_id": "two", "path": "two.sql", "content_sha256": sha},
        ]).to_csv(self.manifest, index=False)
        rows = [self.observation(), self.observation(source_csv=str(source), source_run="20261005"),
                self.observation(query="two", sql_identity="tpcds:two", sql_content_sha256=sha,
                                 source_csv=str(source), source_run="20261005"),
                self.observation(source_csv=str(later), source_run="20261007", timing_status="timeout")]
        with patch.object(refresh.plot, "load", return_value=pd.DataFrame(rows)):
            _, matched, rejected, _ = refresh.current_observations(
                ["old.csv", str(source), str(later)], self.manifest, source)
        self.assertEqual(set(matched["query"]), {"one", "two"})
        self.assertEqual(matched.set_index("query").loc["one", "timing_status"], "timeout")
        self.assertEqual(matched.set_index("query").loc["two", "source_run"], "20261005")
        self.assertEqual(set(rejected.refresh_exclusion),
                         {"superseded_tpcds_batch", "superseded_exact_sql_observation"})

    def test_database_rename_requires_audited_same_host_and_valid_signatures(self):
        evidence = {"family": "TPC-DS", "execution_host": "cpu9", "old_path": "/data/tpcds_db",
                    "new_path": "/data/tpcds_50.duckdb", "size_bytes": 1024, "mtime_ns": 12345}
        for side in ("old", "new"):
            evidence[f"{side}_signature"] = refresh.database_signature(evidence[f"{side}_path"], 1024, 12345)
        rows = pd.DataFrame([self.observation(database_signature=evidence[f"{side}_signature"])
                             for side in ("old", "new")])
        old_signatures = rows.database_signature.copy()
        canonical = refresh.canonical_database_signatures(rows, [evidence])
        self.assertEqual(canonical.unique().tolist(), [evidence["new_signature"]])
        pd.testing.assert_series_equal(rows.database_signature, old_signatures)
        with self.assertRaisesRegex(ValueError, "Invalid old"):
            refresh.canonical_database_signatures(rows, [{**evidence, "size_bytes": 1025}])
        with self.assertRaisesRegex(ValueError, "family/host"):
            refresh.canonical_database_signatures(rows.assign(execution_host="cpu8"), [evidence])

    def test_different_database_signatures_are_not_silently_pooled(self):
        second = self.root / "two.sql"
        second.write_text("SELECT 2;\n")
        sha = refresh.digest(second)
        pd.DataFrame([
            {"query_id": "one", "path": "one.sql", "content_sha256": self.sha},
            {"query_id": "two", "path": "two.sql", "content_sha256": sha},
        ]).to_csv(self.manifest, index=False)
        with self.assertRaisesRegex(ValueError, "Incompatible database_signature"):
            self.load([self.observation(), self.observation(
                query="two", sql_identity="tpcds:two", sql_content_sha256=sha,
                database_signature="another-db")])

    def test_graph_aggregation_is_a_supplementary_control(self):
        pd.DataFrame([{"query_id": "one", "path": "one.sql", "content_sha256": self.sha,
                       "provenance_class": "synthetic_graph"}]).to_csv(self.manifest, index=False)
        _, rows, _, _ = self.load([self.observation(workload_component="structural")])
        self.assertEqual(rows.iloc[0].workload_component, "evaluation")

    def test_explicit_graph_datasets_can_have_distinct_databases(self):
        second = self.root / "two.sql"
        second.write_text("SELECT 2;\n")
        sha = refresh.digest(second)
        pd.DataFrame([
            {"query_id": "one", "path": "one.sql", "content_sha256": self.sha, "graph_dataset": "bitcoin"},
            {"query_id": "two", "path": "two.sql", "content_sha256": sha, "graph_dataset": "epinions"},
        ]).to_csv(self.manifest, index=False)
        rows = [self.observation(family="graph"), self.observation(
            query="two", family="graph", sql_identity="graph:two", sql_content_sha256=sha,
            database_signature="epinions-db", graph_dataset="epinions")]
        _, matched, _, _ = self.load(rows)
        self.assertEqual(set(matched.graph_dataset), {"bitcoin", "epinions"})
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.load([rows[0], {**rows[1], "graph_dataset": "bitcoin"}])
        with self.assertRaisesRegex(ValueError, "Incompatible execution_host"):
            self.load([rows[0], {**rows[1], "execution_host": "cpu8"}])
        with self.assertRaisesRegex(ValueError, "Incompatible timing_samples"):
            self.load([rows[0], {**rows[1], "timing_samples": 5}])

    def test_historical_derived_pattern_is_structural(self):
        pd.DataFrame([{"query_id": "one", "path": "one.sql", "content_sha256": self.sha,
                       "provenance_class": "historical_pattern_adaptation"}]).to_csv(self.manifest, index=False)
        _, rows, _, _ = self.load([self.observation(workload_component="historical_recovery")])
        self.assertEqual(rows.iloc[0].workload_component, "structural")

    def test_source_connected_subgraph_is_structural(self):
        pd.DataFrame([{"query_id": "one", "path": "one.sql", "content_sha256": self.sha,
                       "provenance_class": "source_connected_subgraph"}]).to_csv(self.manifest, index=False)
        _, rows, _, _ = self.load([self.observation()])
        self.assertEqual(rows.iloc[0].workload_component, "structural")
        self.assertEqual(rows.iloc[0].provenance_class, "source_connected_subgraph")


class OutputDirectoryTests(unittest.TestCase):
    def test_query_distribution_uses_manifest_types_and_shapes_for_both_cohorts(self):
        manifest = pd.DataFrame([
            dict(query_id="graph_control", family="graph", query_class="graph", aggregate_variant="", tree_shape="left_deep"),
            dict(query_id="aggregate_count", family="graph", query_class="aggregate", aggregate_variant="grouped_count", tree_shape="bushy"),
            dict(query_id="query_named_bushy", family="tpch", query_class="join", aggregate_variant=None, tree_shape="right_deep"),
        ])
        # The SQL aggregation remains an aggregation even when pushdown is off.
        measured = pd.DataFrame({"query": ["aggregate_count", "query_named_bushy"], "aggregate_pushdown_applied": [0, 0]})
        rows, cross = refresh.query_distribution(manifest, measured)
        totals = {r["cohort"]: r for r in rows if r["family"] == "All"}
        self.assertEqual(totals["active_benchmark"]["total"], 3)
        self.assertEqual(totals["active_benchmark"]["full_queries"], 2)
        self.assertEqual(totals["measured_outeryan"]["aggregation_queries"], 1)
        self.assertEqual(totals["measured_outeryan"]["right_deep"], 1)
        self.assertEqual(totals["measured_outeryan"]["left_deep"], 0)
        for row in rows:
            self.assertEqual(row["total"], row["full_queries"] + row["aggregation_queries"])
            self.assertEqual(row["total"], sum(row[s] for s in ("left_deep", "right_deep", "bushy")))
            self.assertEqual(row["total"], sum(r["n"] for r in cross if r["cohort"] == row["cohort"] and r["family"] == row["family"]))
        tex = refresh.query_distribution_tex(rows)
        self.assertIn(r"\label{tab:query-distribution}", tex)
        self.assertIn("Full & Agg. & LD & RD & Bushy", tex)
        self.assertNotIn("All benchmark queries", tex)
        self.assertIn(r"All & \fix{2} & \fix{1} & \fix{1} & \fix{0} & \fix{1} & \fix{1}", tex)
        self.assertNotIn(r"All & \fix{3}", tex)
        analysis = refresh.query_distribution_discussion_tex(rows)
        self.assertIn(r"\fix{50.00\%}", analysis)
        self.assertNotIn("The benchmark contains", analysis)
        self.assertIn("regardless of whether aggregation is pushed down", analysis)
        for altered in (manifest.assign(tree_shape="unknown"),
                        pd.concat([manifest, manifest.iloc[:1]]),
                        manifest.assign(aggregate_variant="global_count")):
            with self.assertRaises(ValueError):
                refresh.query_distribution(altered, measured)
        with self.assertRaises(ValueError):
            refresh.query_distribution(manifest, pd.DataFrame({"query": ["missing"]}))

    def test_frozen_screen_disclosure_preserves_family_scope_and_equality(self):
        rules = [{"threshold": 0.7, "inclusive": True,
                  "removed_by_family": {"job": 9, "graph": 2}}]
        text = refresh.screening_disclosure_tex(rules)
        self.assertIn(r"\fix{2} Graph and \fix{9} JOB", text)
        self.assertIn(r"at most \fix{$0.7\times$}", text)
        self.assertNotIn("TPC-H", text)
        self.assertNotIn("TPC-DS", text)
        self.assertIn("rather than the optimizer's performance", text)
        self.assertEqual(refresh.screening_disclosure_tex([]), "")

    def test_timeout_retirements_are_disclosed_without_a_speedup_threshold(self):
        rules = refresh.active_performance_screens(refresh.DEFAULT_MANIFEST)
        timeout_rules = [r for r in rules if r.get("kind") == "timeout_retirement"]
        self.assertEqual(len(timeout_rules), 1)
        self.assertEqual(timeout_rules[0]["removed_by_family"], {"graph": 2})
        text = refresh.screening_disclosure_tex(timeout_rules)
        self.assertIn(r"\fix{2} Graph", text)
        self.assertIn("profiling/kernel timeouts", text)
        self.assertNotIn("speed-ups were", text)

    def test_latest_contributing_date_uses_existing_plots_root(self):
        frame = pd.DataFrame({"source_run": ["20261005_201226_t32", "20261002_213551_t32"]})
        self.assertEqual(refresh.output_directory(frame), refresh.plot.DEFAULT_OUTPUT_ROOT / "20261005")

    def test_explicit_directory_is_preserved(self):
        frame = pd.DataFrame({"source_run": ["custom"]})
        self.assertEqual(refresh.output_directory(frame, Path("custom-output")),
                         Path("custom-output").resolve())

    def test_custom_inputs_require_an_explicit_directory(self):
        for runs in ([], ["custom"]):
            with self.subTest(runs=runs), self.assertRaisesRegex(ValueError, "no date"):
                refresh.output_directory(pd.DataFrame({"source_run": runs}))


class ReportingScopeTests(unittest.TestCase):
    def test_pg_footnotes_escape_raw_query_id_fallback(self):
        text = refresh.pg_footnotes_tex([
            {"short_query": "job__storm_13193"}, {"short_query": "Q-H-B-07"},
        ])
        self.assertIn(r"\texttt{job\_\_storm\_13193}", text)
        self.assertNotIn(r"\texttt{job__storm_13193}", text)
        self.assertIn(r"\texttt{Q-H-B-07}", text)
        self.assertIn("separate", text)

    def test_complete_run_does_not_claim_composite_or_verified(self):
        rows = pd.DataFrame({"source_run": ["20261007_161108_t32"] * 3})
        scope = refresh.refresh_scope(rows, active_queries=3, pending_queries=0)
        self.assertIn("One complete source run", scope)
        self.assertIn("no earlier measurements are carried forward", scope)
        self.assertNotIn("optimizer revision", scope)
        self.assertNotIn("composite", scope)

    def test_single_partial_and_multiple_runs_are_distinguished(self):
        partial = pd.DataFrame({"source_run": ["20261007_161108_t32"]})
        self.assertIn("One partial source run", refresh.refresh_scope(partial, 3, 2))
        multiple = pd.DataFrame({"source_run": ["20261005", "20261007"]})
        scope = refresh.refresh_scope(multiple, 2, 0)
        self.assertIn("composite snapshot", scope)
        self.assertIn("do not establish whether optimizer revisions differ", scope)

    def test_unchecked_cohort_is_explicitly_performance_only(self):
        text = refresh.correctness_scope_tex({"measured_correctness_disabled": 100, "measured_verified": 0})
        self.assertIn("Correctness checking was disabled", text)
        self.assertIn("not result-equivalence verification", text)
        self.assertEqual(refresh.correctness_scope_tex({"measured_verified": 100}), "")

    def test_mixed_check_statuses_keep_separate_counts(self):
        text = refresh.correctness_scope_tex({"measured_correctness_disabled": 3, "measured_verified": 4})
        self.assertIn(r"\fix{3} performance-only pairs", text)
        self.assertIn(r"\fix{4} pairs with passed correctness checks", text)


class ExecutionOptimizationTextTests(unittest.TestCase):
    def test_phase_analysis_uses_weighted_shares_not_old_causal_claims(self):
        groups = [{"family": family, "cpu_weighted_fraction": {
            "round1": 0.1, "round2": 0.2, "round3": 0.25, "other": 0.45,
        }} for family in ("Graph", "TPC-H", "TPC-DS", "JOB", "all")]
        text = refresh.phase_discussion_tex(groups)
        self.assertIn(r"remaining operators account for \fix{45.00\%}", text)
        self.assertIn(r"\fix{30.00\%} for the two semi-join rounds combined", text)
        self.assertIn("separate ablation", text)
        self.assertNotIn("most execution work remains in Round", text)
        self.assertNotIn("H-RD-03", text)

    def test_optimizer_maximum_and_counts_are_computed_from_current_sample(self):
        reps = [
            {"short_query": "SHORT", "duckdb_optimizer_ms": 0.5,
             "outeryan_optimizer_ms": 2.0, "outeryan_optimizer_percent": 10.0,
             "outeryan_s": 0.02},
            {"short_query": "LONG", "duckdb_optimizer_ms": 1.0,
             "outeryan_optimizer_ms": 3.0, "outeryan_optimizer_percent": 0.3,
             "outeryan_s": 1.0},
        ]
        text = refresh.optimization_discussion_tex(reps)
        self.assertIn(r"\fix{1 of the 2 queries}", text)
        self.assertIn(r"maximum of \fix{10.00\%}", text)
        self.assertIn(r"\texttt{SHORT}", text)
        self.assertIn(r"\fix{20.000}\,ms of unprofiled running time", text)
        self.assertIn("not uniformly negligible", text)

    def test_section_extraction_leaves_other_paper_sections_out(self):
        section = (r"\subsubsection{Execution Breakdown}" + "\nphase\n"
                   + r"\subsubsection{Optimization Time}" + "\noptimizer\n")
        fragment = "intro\n" + section + r"\subsubsection{PostgreSQL Plan Comparison}" + "\nPG"
        self.assertEqual(refresh.execution_optimization_sections(fragment), section)

    def test_template_defines_actual_profiling_and_runtime_metrics(self):
        section = refresh.execution_optimization_sections(refresh.TEMPLATE.read_text())
        self.assertIn(r"\texttt{all\_optimizers}", section)
        self.assertIn("@@runtime_time@@", section)
        self.assertIn("@@runtime_times@@", section)
        self.assertIn("@@phase_n@@", section)
        self.assertNotIn("single unprofiled post-warmup", section)

    def test_runtime_description_uses_recorded_median_count(self):
        text = refresh.runtime_wording([dict(timing_samples=5, timing_estimator="median_post_warmup")])
        self.assertIn(r"median of \fix{5}", text["runtime_time"])
        self.assertIn("ratio of the two medians", text["runtime_method"])
        self.assertNotIn("single", " ".join(text.values()))

    def test_historical_single_sample_description_is_preserved(self):
        text = refresh.runtime_wording([dict(timing_samples="1", timing_estimator="single_post_warmup")])
        self.assertIn("single unprofiled", text["runtime_time"])
        self.assertNotIn("median", " ".join(text.values()))

    def test_runtime_description_rejects_unknown_or_mixed_protocols(self):
        one = dict(timing_samples=1, timing_estimator="single_post_warmup")
        five = dict(timing_samples=5, timing_estimator="median_post_warmup")
        for records in ([], [one, five], [dict(five, timing_estimator="single_post_warmup")],
                        [dict(five, timing_samples=4)], [dict(five, timing_samples=2.5)]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                refresh.runtime_wording(records)


class PolicyTableTests(unittest.TestCase):
    def setUp(self):
        runtime_filter = patch.object(refresh.plot, "MIN_RUNTIME_SECONDS", 0.0)
        runtime_filter.start()
        self.addCleanup(runtime_filter.stop)

    def test_figure_captions_disclose_screen_and_defaults(self):
        tex = refresh.figure_includes_tex(235, 0.0)
        self.assertIn(r"\fix{235}", tex)
        self.assertIn("matching the performance table and text", tex)
        self.assertIn(r"exact $1\times$ ratios are not plotted", tex)
        self.assertEqual(tex.count(r"\begin{figure*}"), 2)
        self.assertIn("{speedup_all_queries.pdf}", tex)
        self.assertIn("{phase_breakdown_outeryan.pdf}", tex)
        self.assertNotIn("{figures/", tex)
        self.assertNotIn("{figures/", refresh.TEMPLATE.read_text())

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

    def test_defaults_never_change_distribution_or_runtime_sum(self):
        rows = pd.DataFrame([
            {"query": "measured", "family": "TPC-DS", "selected_plan": "OUTERYAN", "correct": "TRUE", "note": "OK",
             "timing_status": "measured", "tm_off": 8.0, "tm_on": 2.0},
            {"query": "skipped", "family": "TPC-DS", "selected_plan": "OUTERYAN", "correct": "TRUE", "note": "FALLBACK-SKIP",
             "timing_status": "fallback-skip", "tm_off": float("nan"), "tm_on": float("nan")},
            {"query": "timeout", "family": "TPC-DS", "selected_plan": "DUCKDB", "correct": "TIMEOUT", "note": "TIMEOUT",
             "timing_status": "timeout", "tm_off": float("nan"), "tm_on": float("nan")},
        ])
        table = refresh.policy_statistics(rows)
        selected = next(row for row in table if row["subset"] == "outeryan_selected" and row["family"] == "All")
        self.assertEqual(selected["n"], 1)
        self.assertEqual(selected["measured"], 1)
        self.assertEqual(selected["policy_defaults"], 0)
        self.assertAlmostEqual(selected["geomean"], 4.0)
        self.assertEqual(selected["total_ratio"], 4.0)
        tex = refresh.runtime_table_tex(table)
        self.assertIn(r"\caption{Statistics across benchmark workloads}", tex)
        self.assertIn("Geomean & Median & Max & Total", tex)
        self.assertNotIn(" & Mean & ", tex)
        self.assertIn(r"\begin{tabular}{lrrrrr}", tex)
        self.assertIn("No default ratios are imputed", tex)
        self.assertNotIn("All valid queries", tex)
        self.assertNotIn("upper/lower", tex)
        self.assertNotIn("excluding measured pairs with both runtimes below", tex)

    def test_cohort_retains_slowdowns_subseconds_and_near_one_not_exact_one(self):
        def row(name, off, on, **kwargs):
            return {"query": name, "family": "TPC-H", "selected_plan": "OUTERYAN", "correct": "TRUE",
                    "note": "OK", "timing_status": "measured", "tm_off": off, "tm_on": on, **kwargs}
        rows = pd.DataFrame([
            row("slow", 0.1, 0.5), row("near", 0.999999, 1.0, speedup=1.0),
            row("unit", 2.0, 2.0), row("native", 20.0, 1.0, selected_plan="DUCKDB"),
            row("bad", 20.0, 1.0, correct="FALSE"),
            row("unchecked", 4.0, 1.0, correct="NOT-CHECKED", correctness_check="disabled"),
            row("unknown", 4.0, 1.0, correct="NOT-CHECKED"),
        ])
        cohort, excluded = refresh.reporting_cohort(rows)
        self.assertEqual(set(cohort["query"]), {"slow", "near", "unchecked"})
        reasons = excluded.set_index("query").reporting_exclusion.to_dict()
        self.assertEqual(reasons["unit"], "exact_unit_speedup")
        self.assertEqual(reasons["native"], "not_outeryan_selected")
        self.assertEqual(reasons["bad"], "correctness_not_true")
        self.assertEqual(reasons["unknown"], "correctness_not_true")
        table = refresh.policy_statistics(rows)
        total = next(row for row in table if row["family"] == "All")
        self.assertEqual(total["n"], len(cohort))
        self.assertAlmostEqual(total["geomean"], (0.2 * 0.999999 * 4.0) ** (1 / 3))
        summary = refresh.plot.summarize(refresh.plot.prepare_queries(cohort, "tm"))
        self.assertEqual(total["n"], summary["counts"]["valid"])
        self.assertEqual(total["geomean"], summary["speedup"]["geomean"])

    def test_intro_and_benchmark_definition_do_not_claim_imputed_cohort(self):
        template = refresh.TEMPLATE.read_text()
        self.assertIn("Our benchmark contains @@benchmark_n@@ query instances", template)
        self.assertIn("Over @@selected_n@@ @@runtime_cohort@@ queries", template)
        self.assertNotIn("while the remaining queries run", template)
        self.assertIn("Full active SQL manifest", template)


if __name__ == "__main__":
    unittest.main()
