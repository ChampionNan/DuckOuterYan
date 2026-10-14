"""Membership curation is exact, reproducible, and separate from new candidates."""
from collections import Counter
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import balanced_benchmark as b
import benchmark_plan_cohort as c
from benchmark_corpus import resolve_sql_path
import prepare_grouping_candidates as grouping
from test_gen_outerjoin_benchmark import forbid_result_access


class PlanCohortTest(unittest.TestCase):
    def test_policy_retires_both_timeouts_and_excludes_small_fallbacks(self):
        spec = c.policy()
        old = {r["query_id"]: r for r in c.archived_rows(spec)}
        selected = [r for r in spec["members"] if r["role"] == "selected"]
        controls = [r for r in spec["members"] if r["role"] == "cost_control"]
        self.assertEqual(len(selected), 285)
        retired = [r for r in spec["members"] if r["removal_reason"] == "both_engines_timeout"]
        self.assertEqual(len(retired), 21)
        self.assertTrue(all(r["role"] == "removed" and r["family"] == "graph" for r in retired))
        self.assertEqual(len(controls), 65)
        self.assertEqual(sum(int(old[r["query_id"]]["relation_count"]) == 3 for r in selected), 6)
        self.assertTrue(all(r["reference_selected_plan"] == "OUTERYAN" for r in selected))
        self.assertTrue(all(r["reference_decision_reason"] == "COST_DUCKDB_BETTER"
                            and int(old[r["query_id"]]["relation_count"]) > 3 for r in controls))
        self.assertEqual(spec["expected_counts_after"], dict(graph=67, tpch=87, tpcds=87, job=109))
        self.assertTrue(all(r["role"] == "removed" for r in spec["members"]
                            if r["reference_decision_reason"] in ("DUCKDB_PLAN", "INAPPLICABLE")))

    def test_controls_reproducible_and_ignore_timing_fields(self):
        spec = c.policy()
        rows = c.archived_rows(spec)
        decisions = {r["query_id"]: dict(selected_plan=r["reference_selected_plan"],
                                         decision_reason=r["reference_decision_reason"], tm_speedup="999")
                     for r in spec["members"]}
        first = {r["query_id"] for r in c.choose_controls(rows, decisions)}
        for r in decisions.values():
            r["tm_speedup"] = "0.001"
        second = {r["query_id"] for r in c.choose_controls(list(reversed(rows)), decisions)}
        self.assertEqual(first, second)
        self.assertEqual(first, {r["query_id"] for r in spec["members"] if r["role"] == "cost_control"})

    def test_generation_uses_no_result_files_and_preserves_sql(self):
        with tempfile.TemporaryDirectory() as temp, forbid_result_access(), contextlib.redirect_stdout(io.StringIO()):
            root = Path(temp)
            self.assertEqual(b.generate(root), 350)
            rows = b.validate(root / "benchmark")
            self.assertEqual(len(rows), 350)
            for row in rows:
                self.assertEqual((root / "benchmark" / row["path"]).read_bytes(),
                                 (c.ARCHIVE / row["path"]).read_bytes())
            before = (root / "benchmark/manifest.csv").read_bytes()
            b.generate(root)
            self.assertEqual(before, (root / "benchmark/manifest.csv").read_bytes())
            removed = next(r for r in c.policy()["members"] if r["role"] == "removed")
            (root / "benchmark" / removed["path"]).write_bytes((c.ARCHIVE / removed["path"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "file set"):
                b.validate(root / "benchmark")

    def test_candidates_are_new_semantics_not_members(self):
        with forbid_result_access():
            rows, contents, coverage = grouping.candidate_definitions()
        originals = {r["query_id"]: r for r in c.archived_rows(c.policy())}
        self.assertEqual(len(coverage), 139)
        self.assertTrue(rows)
        self.assertTrue({r["query_id"] for r in rows}.isdisjoint(originals))
        self.assertEqual(len({r["sql_fingerprint"] for r in rows}), len(rows))
        for row in rows:
            original = originals[row["grouping_source_query"]]
            self.assertGreater(int(row["relation_count"]), 3)
            self.assertEqual(Counter(row["join_vector"]), Counter(original["join_vector"]))
            self.assertNotEqual(row["join_vector"], original["join_vector"])
            self.assertEqual(grouping.masked_structure(contents[row["path"]]),
                             grouping.masked_structure((c.ARCHIVE / original["path"]).read_text()))
            self.assertEqual(row["selectivity_predicate"], original["selectivity_predicate"])
            self.assertEqual(row["qualification_status"], "PENDING_TARGET_PLAN_AND_MEASUREMENT")

    def test_removed_sql_resolves_to_archive(self):
        for row in c.policy()["members"]:
            if row["role"] == "removed":
                resolved = resolve_sql_path("join", row["path"])
                self.assertEqual(b.digest(resolved), row["content_sha256"])


if __name__ == "__main__":
    unittest.main()
