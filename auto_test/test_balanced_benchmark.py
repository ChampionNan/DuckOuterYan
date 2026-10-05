"""Candidate construction and qualification tests; never run the expensive corpus."""
from collections import Counter
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import balanced_benchmark as b
from benchmark_corpus import count_base_relations
import qualify_benchmark as q
import tpcds_refresh as refresh
from test_gen_outerjoin_benchmark import forbid_result_access


class BalancedBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = json.loads(b.DESIGN.read_text())
        cls.evidence = json.loads(b.EVIDENCE.read_text())
        cls.groups = b.candidate_rows(cls.design, cls.evidence)

    def test_active_matrix_and_mixed_kinds(self):
        rows = b.validate(b.ROOT / "benchmark")
        self.assertEqual(len(rows), 741)
        self.assertEqual(Counter(r["family"] for r in rows), dict(graph=180, tpch=180, tpcds=201, job=180))
        self.assertEqual(Counter((r["family"], r["semantic_tier"], r["tree_shape"]) for r in rows if r["family"] != "tpcds"),
                         {(f, t, s):20 for f in ("graph", "tpch", "job") for t in b.TIERS for s in b.SHAPES})
        self.assertTrue(all(len(set(r["join_vector"])) >= 2 for r in rows))
        self.assertFalse(any(r["source_seed"] == "tpcds_q72_fulfillment" for r in rows))
        self.assertEqual(self.design["curation"]["timeout_seconds"], 600)
        self.assertTrue(all(r["qualification_timeout_seconds"] == "600" for r in rows))
        graph = [r for r in rows if r["family"] == "graph"]
        self.assertEqual(Counter(int(r["relation_count"]) for r in graph), {4: 126, 5: 54})
        for tier in b.TIERS:
            for shape in b.SHAPES:
                self.assertEqual(Counter(int(r["relation_count"]) for r in graph
                                         if r["semantic_tier"] == tier and r["tree_shape"] == shape),
                                 {4: 14, 5: 6})
        self.assertIn("industry_synthetic_control", {r["provenance_class"] for r in rows})
        banned = {e["expression_fingerprint"] for e in self.evidence["excluded"]}
        self.assertTrue(banned.isdisjoint(r["expression_fingerprint"] for r in rows if not refresh.is_recovery(r)))

    def test_historical_cases_preserve_sql_and_are_not_band_calibrated(self):
        active = b.ROOT / "benchmark"
        self.assertFalse(any(b.is_historical_case(r) for r in b.validate(active)))
        self.assertEqual((active / "historical_cases.txt").read_text(), "")
        corpus = b.ROOT / "revisions/retired_tpcds_20261005/benchmark"
        rows = [r for r in b.read_manifest(corpus / "manifest.csv") if b.is_historical_case(r)]
        self.assertEqual(len(rows), 3)
        for row in rows:
            original = b.legacy.REPO_ROOT / row["source_location"]
            self.assertEqual((corpus / row["path"]).read_bytes(), original.read_bytes())
            self.assertEqual(row["semantic_tier"], "historical_unbanded")
            self.assertEqual(row["target_min_fraction"], "")
            self.assertEqual(row["target_max_fraction"], "")
            self.assertEqual(row["calibration_in_range"], "not_applicable")
            self.assertEqual(row["qualification_status"], "PENDING_CPU9_MEASUREMENT")

    def test_graph_caps_filter_each_non_anchor_input_without_changing_join_structure(self):
        corpus = b.ROOT / "benchmark"
        for row in b.read_manifest(corpus / "manifest.csv"):
            if row["family"] != "graph":
                continue
            sql = (corpus / row["path"]).read_text()
            inputs = json.loads(row["input_filter_profiles_json"])
            self.assertEqual(len(inputs), int(row["relation_count"]) - 1)
            self.assertEqual(count_base_relations(sql), int(row["relation_count"]))
            self.assertIn("__inputcap1__", row["query_id"])
            self.assertEqual(b.expression_key(sql, "graph"), row["expression_fingerprint"])
            outer_where = sql.split("\nWHERE ")[-1].split("\nGROUP BY")[0].rstrip(";\n")
            self.assertEqual(outer_where, row["selectivity_predicate"])
            cap = (10, 20, 40)[b.TIERS.index(row["semantic_tier"])]
            for extra in inputs:
                alias = extra["relation"]
                self.assertNotEqual(alias, "R1")
                self.assertIn(f"(SELECT src, dst FROM {alias} WHERE src <= {cap}) {alias}", sql)
                self.assertEqual(extra["predicate"], f"{alias}.src <= {cap}")
                self.assertLess(extra["calibration_fraction"], .3)

    def test_reserve_generation_does_not_repeat_historical_cases(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), forbid_result_access():
            root = Path(tmp)
            b.generate(root, per_family=9, batch=1)
            rows = b.validate(root / "benchmark")
            self.assertEqual(len(rows), 36)
            self.assertFalse(any(b.is_historical_case(r) for r in rows))
            self.assertEqual((root / "benchmark/historical_cases.txt").read_text(), "")

    def test_composite_edges_are_complete(self):
        predicate = "a.item = b.item AND a.ticket = b.ticket AND a.store = b.store"
        self.assertEqual(b.full_equality(predicate), predicate)

    def test_graph_branch_is_not_star_and_can_be_bushy(self):
        seeds = [s for s in b.graph_seeds() if s.topology == "branch"]
        self.assertTrue(seeds)
        for seed in seeds:
            self.assertIsNotNone(b.legacy.bushy_root_partition(seed))

    def test_bands_have_no_overlap_and_cap_at_sixty(self):
        bands = self.design["tiers"]
        for fraction, expected in ((0, []), (.04, ["low"]), (.05, ["medium"]),
                                   (.4, ["high"]), (.6, ["high"]), (.61, [])):
            self.assertEqual([s["name"] for s in bands if b.legacy.fraction_in_band(fraction, s)], expected)

    def test_disjoint_reserve_batch(self):
        first = {g[0]["expression_fingerprint"] for g in b.select_groups(self.groups, batch=0)}
        second = {g[0]["expression_fingerprint"] for g in b.select_groups(self.groups, batch=1)}
        self.assertEqual(len(first), 240)
        self.assertEqual(len(second), 240)
        self.assertTrue(first.isdisjoint(second))

    def test_reproducible_without_result_access_and_refuses_edits(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), forbid_result_access():
            root = Path(tmp)
            b.generate(root)
            manifest = root / "benchmark/manifest.csv"
            self.assertEqual(manifest.read_bytes(), (b.ROOT / "benchmark/manifest.csv").read_bytes())
            b.generate(root)
            row = b.read_manifest(manifest)[0]
            (root / "benchmark" / row["path"]).write_text("SELECT 1;")
            with self.assertRaisesRegex(ValueError, "Locally edited"):
                b.generate(root)


class QualificationTest(unittest.TestCase):
    def setUp(self):
        self.candidate = dict(content_sha256="sql", selectivity_profile="p", semantic_tier="low")
        self.audit = dict(execution_host="cpu9", manifest_sha256="manifest",
                          design_sha256=b.digest(b.DESIGN), profiles=[dict(profile="p", tier="low",
                          in_range=True, database_signature="db")])
        self.result = dict(corpus_revision=b.REVISION, sql_content_sha256="sql", corpus_manifest_sha256="manifest",
                           execution_host="cpu9", database_signature="db", timeout_seconds="600", correct="TRUE",
                           timing_status="measured", note="OK", tm_off="8", tm_on="10")

    def status(self, **changes):
        return q.classify(self.candidate, dict(self.result, **changes), self.audit, "manifest")

    def test_boundaries_and_missing_data(self):
        self.assertEqual(self.status(), "eligible")
        self.assertEqual(self.status(tm_off="7.999"), "speedup_below_0.8")
        self.assertEqual(self.status(tm_off="1", tm_on="1"), "runtime_not_above_1s")
        self.assertEqual(self.status(tm_off="599.9", tm_on="599.9"), "eligible")
        self.assertEqual(self.status(tm_on="600"), "runtime_at_or_above_timeout")
        self.assertEqual(self.status(tm_on="nan"), "invalid_timing")
        self.assertEqual(q.classify(self.candidate, None, self.audit, "manifest"), "pending_measurement")

    def test_tpcds_refresh_keeps_subsecond_and_half_speed_boundary(self):
        self.candidate.update(qualification_min_runtime_s="0", qualification_min_speedup="0.5")
        self.assertEqual(self.status(tm_off="0.1", tm_on="0.2"), "eligible")
        self.assertEqual(self.status(tm_off="0.0999", tm_on="0.2"), "speedup_below_0.5")
        self.candidate["qualification_min_runtime_s"] = "nan"
        self.assertEqual(self.status(), "invalid_qualification_policy")

    def test_failures_never_become_measured(self):
        self.assertEqual(self.status(note="OFF-TIMEOUT"), "timeout_at_600s")
        self.assertEqual(self.status(timing_status="fallback-skip", tm_off="NA"), "fallback_not_measured")
        self.assertEqual(self.status(timeout_seconds="900", note="TIMEOUT"), "requires_600s_run")
        self.assertEqual(self.status(timeout_seconds="1800"), "requires_600s_run")
        self.assertEqual(self.status(duckdb_timeout_seconds="600", outeryan_timeout_seconds="900"), "requires_600s_run")
        self.assertEqual(self.status(correct="FALSE"), "correctness_not_verified")

    def test_evidence_identity(self):
        self.assertEqual(self.status(execution_host="local"), "host_mismatch")
        self.assertEqual(self.status(sql_content_sha256="changed"), "sql_or_revision_mismatch")
        self.assertEqual(self.status(corpus_manifest_sha256="changed"), "manifest_mismatch")
        self.assertEqual(self.status(database_signature="changed"), "database_mismatch")
        self.audit["profiles"][0]["in_range"] = False
        self.assertEqual(self.status(), "selectivity_unverified_or_out_of_band")

    def test_unchecked_performance_requires_explicit_opt_out(self):
        self.assertEqual(self.status(correct="NOT-CHECKED"), "correctness_not_verified")
        self.assertEqual(self.status(correct="NOT-CHECKED", correctness_check="disabled"), "eligible")
        self.assertEqual(self.status(correct="FALSE", correctness_check="disabled"), "correctness_not_verified")

    def test_graph_qualification_requires_every_input_cap_audit(self):
        extra = dict(profile="graph_aux_source_range", relation="R2", predicate="R2.src <= 10")
        self.candidate["input_filter_profiles_json"] = json.dumps([extra])
        self.assertEqual(self.status(), "input_selectivity_unverified_or_out_of_band")
        self.audit["profiles"].append(dict(extra, tier="low", in_range=True, database_signature="db"))
        self.assertEqual(self.status(), "eligible")
        self.audit["profiles"][-1]["predicate"] = "R2.src <= 40"
        self.assertEqual(self.status(), "input_selectivity_predicate_mismatch")
        self.audit["profiles"][-1]["predicate"] = extra["predicate"]
        self.audit["profiles"][-1]["database_signature"] = "changed"
        self.assertEqual(self.status(), "database_mismatch")

    def test_graph_input_audit_counts_each_relation_against_its_own_band(self):
        rows = b.read_manifest(b.ROOT / "benchmark/manifest.csv")
        candidate = next(r for r in rows if r["family"] == "graph" and r["relation_count"] == "4"
                         and r["semantic_tier"] == "high")
        def run_count(command, **kwargs):
            sql = command[-1]
            is_anchor = " FROM R1;" in sql
            self.assertIn("R1.src <= 306" if is_anchor else "src <= 40", sql)
            return mock.Mock(stdout=json.dumps([dict(n=24186, c0=13299 if is_anchor else 5126)]))
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(b, "validate", return_value=[candidate]), \
                mock.patch.object(q, "database_signature", return_value="db"), \
                mock.patch.object(q.subprocess, "run", side_effect=run_count) as run:
            output = Path(tmp) / "audit.json"
            self.assertTrue(q.audit_selectivity(b.ROOT, Path("duckdb"), output, 10))
            profiles = json.loads(output.read_text())["profiles"]
            self.assertEqual(run.call_count, 4)
            self.assertEqual({p["relation"] for p in profiles}, {"", "R2", "R3", "R4"})
            self.assertTrue(all(p["in_range"] for p in profiles))

    def test_pending_report_has_no_invented_speedup(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            report = q.qualify([b.ROOT / "benchmark"], [], [], Path(tmp))
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertEqual(report["selected"], 0)
            self.assertTrue(all(c["shortage"] == 60 for c in report["coverage"]))
            self.assertTrue(all(s["geomean"] is None for s in report["statistics"].values()))
            self.assertEqual(report["balanced_candidates"], 741)
            self.assertEqual(report["historical_supplementary_candidates"], 0)
            self.assertEqual(report["historical_supplementary_observations"], 0)
            self.assertEqual(report["qualification_timeout_seconds"], 600)

    def test_historical_results_preserved_separately_including_timeouts(self):
        candidates = [r for r, _ in b.historical_cases()]
        results = [dict(self.result, family=r["family"], query=r["query_id"],
                        note="OFF-TIMEOUT" if i == 0 else "OK", tm_off="NA" if i == 0 else "712.5")
                   for i, r in enumerate(candidates)]
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            b.generate(root, per_family=9)
            corpus = root / "benchmark"
            source = root / "results.csv"
            b.write_csv(source, results)
            report = q.qualify([corpus], [], [source], root / "report")
            self.assertEqual(report["selected"], 0)
            self.assertEqual(report["historical_supplementary_observations"], 3)
            supplementary = b.read_manifest(root / "report/supplementary_results.csv")
            self.assertEqual(len(supplementary), 3)
            self.assertEqual(supplementary[0]["note"], "OFF-TIMEOUT")
            self.assertEqual(supplementary[0]["tm_off"], "NA")
            self.assertEqual(supplementary[1]["tm_off"], "712.5")
            self.assertTrue(all(r["evaluation_role"] == b.HISTORICAL_ROLE for r in supplementary))

    def test_band_audit_explicitly_excludes_historical_cases(self):
        rows = b.read_manifest(b.ROOT / "benchmark/manifest.csv")
        candidate = next(r for r in rows if not b.is_historical_case(r) and r["family"] != "graph")
        historical = [r for r, _ in b.historical_cases()]
        design = json.loads(b.DESIGN.read_text())
        calibration = design["profiles"][candidate["selectivity_profile"]]["calibration"]
        counts = dict(n=calibration["n"], c0=calibration["qualified_rows"][b.TIERS.index(candidate["semantic_tier"])])
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(b, "validate", return_value=[candidate] + historical), \
                mock.patch.object(q, "database_signature", return_value="db"), \
                mock.patch.object(q.subprocess, "run", return_value=mock.Mock(stdout=json.dumps([counts]))) as run:
            output = Path(tmp) / "audit.json"
            self.assertTrue(q.audit_selectivity(b.ROOT, Path("duckdb"), output, 600))
            report = json.loads(output.read_text())
            self.assertEqual(report["historical_cases_outside_band_audit"], [r["query_id"] for r in historical])
            self.assertEqual(len(report["profiles"]), 1)
            self.assertEqual(run.call_count, 1)
            self.assertNotIn("% 1000", run.call_args[0][0][-1])

    def test_latest_failure_replaces_prior_success_in_report(self):
        corpus = b.ROOT / "benchmark"
        candidate = next(r for r in b.read_manifest(corpus / "manifest.csv") if r["family"] != "graph")
        manifest_hash = b.digest(corpus / "manifest.csv")
        audit = dict(self.audit, manifest_sha256=manifest_hash, profiles=[dict(
            profile=candidate["selectivity_profile"], tier=candidate["semantic_tier"],
            in_range=True, database_signature="db")])
        result = dict(self.result, family=candidate["family"], query=candidate["query_id"],
                      corpus_manifest_sha256=manifest_hash, sql_content_sha256=candidate["content_sha256"],
                      selected_plan="OUTERYAN", timing_threads="32", formula_id="TEST")
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            audit_path = root / "audit.json"
            b.write_json(audit_path, audit)
            first, last = root / "first.csv", root / "last.csv"
            b.write_csv(first, [result])
            b.write_csv(last, [dict(result, note="ON-TIMEOUT", tm_on="NA")])
            passed = q.qualify([corpus], [audit_path], [first], root / "pass")
            self.assertEqual(passed["selected"], 1)
            retained = b.read_manifest(root / "pass/qualified_results.csv")
            self.assertEqual(retained[0]["qualification_policy"], "performance_screened")
            self.assertEqual((root / "pass/qualified_query_paths.txt").read_text().strip(), candidate["path"])
            failed = q.qualify([corpus], [audit_path], [first, last], root / "fail")
            self.assertEqual(failed["selected"], 0)
            self.assertEqual(failed["reasons"]["timeout_at_600s"], 1)


if __name__ == "__main__":
    unittest.main()
