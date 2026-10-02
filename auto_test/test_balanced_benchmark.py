"""Candidate construction and qualification tests; never run the expensive corpus."""
from collections import Counter
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import balanced_benchmark as b
import qualify_benchmark as q
from test_gen_outerjoin_benchmark import forbid_result_access


class BalancedBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = json.loads(b.DESIGN.read_text())
        cls.evidence = json.loads(b.EVIDENCE.read_text())
        cls.groups = b.candidate_rows(cls.design, cls.evidence)

    def test_active_matrix_and_mixed_kinds(self):
        rows = b.validate(b.ROOT / "benchmark")
        self.assertEqual(len(rows), 720)
        self.assertEqual(Counter((r["family"], r["semantic_tier"], r["tree_shape"]) for r in rows),
                         {(f, t, s):20 for f in b.FAMILIES for t in b.TIERS for s in b.SHAPES})
        self.assertTrue(all(len(set(r["join_vector"])) >= 2 for r in rows))
        self.assertFalse(any(r["source_seed"] == "tpcds_q72_fulfillment" for r in rows))
        self.assertIn("industry_synthetic_control", {r["provenance_class"] for r in rows})
        banned = {e["expression_fingerprint"] for e in self.evidence["excluded"]}
        self.assertTrue(banned.isdisjoint(r["expression_fingerprint"] for r in rows))

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
                           execution_host="cpu9", database_signature="db", timeout_seconds="1800", correct="TRUE",
                           timing_status="measured", note="OK", tm_off="8", tm_on="10")

    def status(self, **changes):
        return q.classify(self.candidate, dict(self.result, **changes), self.audit, "manifest")

    def test_boundaries_and_missing_data(self):
        self.assertEqual(self.status(), "eligible")
        self.assertEqual(self.status(tm_off="7.999"), "speedup_below_0.8")
        self.assertEqual(self.status(tm_off="1", tm_on="1"), "runtime_not_above_1s")
        self.assertEqual(self.status(tm_on="1800"), "runtime_at_or_above_timeout")
        self.assertEqual(self.status(tm_on="nan"), "invalid_timing")
        self.assertEqual(q.classify(self.candidate, None, self.audit, "manifest"), "pending_measurement")

    def test_failures_never_become_measured(self):
        self.assertEqual(self.status(note="OFF-TIMEOUT"), "timeout_at_1800s")
        self.assertEqual(self.status(timing_status="fallback-skip", tm_off="NA"), "fallback_not_measured")
        self.assertEqual(self.status(timeout_seconds="600", note="TIMEOUT"), "requires_1800s_run")
        self.assertEqual(self.status(correct="FALSE"), "correctness_not_verified")

    def test_evidence_identity(self):
        self.assertEqual(self.status(execution_host="local"), "host_mismatch")
        self.assertEqual(self.status(sql_content_sha256="changed"), "sql_or_revision_mismatch")
        self.assertEqual(self.status(corpus_manifest_sha256="changed"), "manifest_mismatch")
        self.assertEqual(self.status(database_signature="changed"), "database_mismatch")
        self.audit["profiles"][0]["in_range"] = False
        self.assertEqual(self.status(), "selectivity_unverified_or_out_of_band")

    def test_pending_report_has_no_invented_speedup(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            report = q.qualify([b.ROOT / "benchmark"], [], [], Path(tmp))
            self.assertEqual(report["status"], "INCOMPLETE")
            self.assertEqual(report["selected"], 0)
            self.assertTrue(all(c["shortage"] == 60 for c in report["coverage"]))
            self.assertTrue(all(s["geomean"] is None for s in report["statistics"].values()))

    def test_latest_failure_replaces_prior_success_in_report(self):
        corpus = b.ROOT / "benchmark"
        candidate = b.read_manifest(corpus / "manifest.csv")[0]
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
            self.assertEqual(failed["reasons"]["timeout_at_1800s"], 1)


if __name__ == "__main__":
    unittest.main()
