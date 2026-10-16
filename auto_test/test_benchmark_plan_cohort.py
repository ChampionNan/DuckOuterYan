"""Membership curation is exact, reproducible, and separate from new candidates."""
import contextlib
import io
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

import balanced_benchmark as b
import benchmark_plan_cohort as c
from benchmark_corpus import resolve_sql_path
from verify_benchmark_reproduction import snapshot
from test_gen_outerjoin_benchmark import forbid_result_access


class PlanCohortTest(unittest.TestCase):
    def test_dependency_normalization_only_accepts_pinned_generator_revision(self):
        source = c.ARCHIVE / "speedup_excluded.csv"
        rows = b.read_manifest(b.ROOT / "benchmark/speedup_excluded.csv")
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / source.name
            b.write_csv(target, rows)
            self.assertTrue(c.same_dependency(source, target))
            synthetic = next(r for r in rows
                             if r["source_location"] == "auto_test/balanced_benchmark.py")
            self.assertEqual(synthetic["source_sha256"], b.SYNTHETIC_SOURCE_SHA256)
            synthetic["source_sha256"] = "0" * 64
            b.write_csv(target, rows)
            self.assertFalse(c.same_dependency(source, target))
            synthetic["source_sha256"] = b.SYNTHETIC_SOURCE_SHA256
            synthetic["source_query"] = "modified definition"
            b.write_csv(target, rows)
            self.assertFalse(c.same_dependency(source, target))

    def test_policy_retires_both_timeouts_and_excludes_small_fallbacks(self):
        spec = c.policy()
        old = {r["query_id"]: r for r in c.archived_rows(spec)}
        selected = [r for r in spec["members"] if r["role"] == "selected"]
        controls = [r for r in spec["members"] if r["role"] == "cost_control"]
        self.assertEqual(len(selected), 282)
        retired = [r for r in spec["members"] if r["removal_reason"] == "both_engines_timeout"]
        self.assertEqual(len(retired), 21)
        self.assertTrue(all(r["role"] == "removed" and r["family"] == "graph" for r in retired))
        self.assertEqual(len(controls), 39)
        self.assertEqual(sum(int(old[r["query_id"]]["relation_count"]) == 3 for r in selected), 6)
        self.assertTrue(all(r["reference_selected_plan"] == "OUTERYAN" for r in selected))
        self.assertTrue(all(r["reference_decision_reason"] == "COST_DUCKDB_BETTER"
                            and int(old[r["query_id"]]["relation_count"]) > 3 for r in controls))
        self.assertEqual(spec["expected_counts_after"], dict(graph=67, tpch=86, tpcds=61, job=107))
        job = next(r for r in spec["members"] if r["query_id"] == c.RETIRED_JOB_QUERY)
        self.assertEqual((job["role"], job["removal_reason"]), ("removed", c.JOB_RETIREMENT_REASON))
        minima = [r for r in spec["members"] if r["query_id"] in c.RETIRED_FAMILY_MINIMA]
        self.assertEqual(len(minima), 2)
        self.assertTrue(all(r["role"] == "removed" and
                            r["removal_reason"] == c.FAMILY_MINIMUM_RETIREMENT_REASON for r in minima))
        self.assertTrue(all(r["role"] == "removed" for r in spec["members"]
                            if r["reference_decision_reason"] in ("DUCKDB_PLAN", "INAPPLICABLE")))

    def test_controls_reproducible_and_ignore_timing_fields(self):
        spec = c.policy()
        rows = c.archived_rows(spec)
        decisions = {r["query_id"]: dict(selected_plan=r["reference_selected_plan"],
                                         decision_reason=r["reference_decision_reason"], tm_speedup="999")
                     for r in spec["members"]}
        initial = c.choose_controls(rows, decisions)
        first = {r["query_id"] for r in c.deduplicate_tpcds_controls(initial)}
        for r in decisions.values():
            r["tm_speedup"] = "0.001"
        second = {r["query_id"] for r in c.deduplicate_tpcds_controls(
            c.choose_controls(list(reversed(rows)), decisions))}
        self.assertEqual(first, second)
        self.assertEqual(first, {r["query_id"] for r in spec["members"] if r["role"] == "cost_control"})

    def test_tpcds_controls_cover_each_source_shape_once(self):
        spec = c.policy()
        metadata = {r["query_id"]: r for r in c.archived_rows(spec)}
        controls = [metadata[r["query_id"]] for r in spec["members"] if r["role"] == "cost_control"]
        removed = [metadata[r["query_id"]] for r in spec["members"]
                   if r["removal_reason"] == c.DEDUP_REMOVAL_REASON]
        self.assertEqual(len(removed), 26)
        self.assertTrue(all(r["family"] == "tpcds" for r in removed))
        ds = [r for r in controls if r["family"] == "tpcds"]
        keys = [(r["source_seed"], r["tree_shape"]) for r in ds]
        self.assertEqual(len(keys), 16)
        self.assertEqual(len(set(keys)), 16)
        self.assertTrue(all((r["source_seed"], r["tree_shape"]) in keys for r in removed))
        self.assertEqual(c.deduplicate_tpcds_controls(controls), sorted(controls, key=lambda r: r["query_id"]))

    def test_generation_uses_no_result_files_and_preserves_sql(self):
        with tempfile.TemporaryDirectory() as temp, forbid_result_access(), contextlib.redirect_stdout(io.StringIO()):
            root = Path(temp)
            self.assertEqual(b.generate(root), 321)
            rows = b.validate(root / "benchmark")
            self.assertEqual(len(rows), 321)
            self.assertNotIn(c.RETIRED_JOB_QUERY, {r["query_id"] for r in rows})
            self.assertTrue(c.RETIRED_FAMILY_MINIMA.isdisjoint(r["query_id"] for r in rows))
            updates = {r["query_id"]: r for r in c.query_updates.policy()["replacements"]}
            unchanged = 0
            for row in rows:
                if row["query_id"] in updates:
                    self.assertEqual(b.digest(root / "benchmark" / row["path"]),
                                     updates[row["query_id"]]["content_sha256"])
                else:
                    self.assertEqual((root / "benchmark" / row["path"]).read_bytes(),
                                     (c.ARCHIVE / row["path"]).read_bytes())
                    unchanged += 1
            self.assertEqual(unchanged, 316)
            before = (root / "benchmark/manifest.csv").read_bytes()
            b.generate(root)
            self.assertEqual(before, (root / "benchmark/manifest.csv").read_bytes())
            removed = next(r for r in c.policy()["members"] if r["role"] == "removed")
            (root / "benchmark" / removed["path"]).write_bytes((c.ARCHIVE / removed["path"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "file set"):
                b.validate(root / "benchmark")

    def test_predicate_updates_preserve_structure_and_identity_provenance(self):
        with forbid_result_access():
            original = {r["query_id"]: r for r in c.archived_rows(c.policy())}
            for entry in c.query_updates.policy()["replacements"]:
                old = original[entry["original_query"]]
                row, sql = c.query_updates.definition(old, entry)
                source = (c.ARCHIVE / old["path"]).read_text()
                if entry.get("rewrite") == "duplicate_orders_date_input":
                    scan = "(SELECT * FROM orders WHERE {}) AS orders".format(
                        old["selectivity_predicate"].replace("orders.", ""))
                    self.assertEqual(sql.replace("LEFT OUTER JOIN " + scan + " ON",
                                                 "LEFT OUTER JOIN orders   ON"), source)
                    self.assertEqual(sql.count("WHERE " + old["selectivity_predicate"]), 1)
                    self.assertEqual(row["selectivity_predicate"], old["selectivity_predicate"])
                    self.assertEqual(row["input_filter_placement"], "orders input plus unchanged outer WHERE")
                else:
                    self.assertEqual(sql.replace(row["selectivity_predicate"], "PREDICATE"),
                                     source.replace(old["selectivity_predicate"], "PREDICATE"))
                self.assertEqual(row["replaces_content_sha256"], old["content_sha256"])
                self.assertEqual(row["semantic_tier"], entry["semantic_tier"])
                for key in ("relation_count", "tree_shape", "join_vector", "source_seed"):
                    self.assertEqual(row[key], old[key])
                self.assertEqual(row["content_sha256"], entry["measurement_content_sha256"])

    def test_terminal_selectivity_suffix_is_renamed(self):
        entries = c.query_updates.policy()["replacements"]
        entry = next(e for e in entries if "where_d180" in e["measurement_query"])
        old = next(r for r in c.archived_rows(c.policy()) if r["query_id"] == entry["original_query"])
        row, _ = c.query_updates.definition(old, entry)
        self.assertTrue(old["query_id"].endswith("__sel_high"))
        self.assertTrue(row["query_id"].endswith("__sel_medium"))
        self.assertEqual(row["calibration_qualified_rows"], "22439342")
        with self.assertRaisesRegex(ValueError, "name does not match its tier"):
            c.query_updates.definition(old, dict(entry, query_id=old["query_id"]))

    def test_cli_rebuild_keeps_approved_tpch_predicates(self):
        approved = {
            "__sub075_20261015_where_d180": "ad7b9b33d02875d26c3de5aa42b6278c8b1bfe8ff5e3f68b977a6846b645013a",
            "__sub075_20261015_where_d110_1995": "7a06d04ae49bf5296516535a31de34a260e3a6eb89efac6621aeec952420750f",
            "__sub075_20261015_where_d930_1992": "ad2a706d6ad222847a11fb46cbe7cb20288aefecd5042d4b6ba64c23f1f7afba",
        }
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(Path(b.__file__).with_name("gen_outerjoin_benchmark.py")),
                 "--root", temp], text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = Path(temp) / "benchmark"
            rows = {r["query_id"]: r for r in b.validate(output)}
            self.assertEqual(len(rows), 321)
            self.assertEqual(snapshot(output), snapshot(b.ROOT / "benchmark"))
            for suffix, sha in approved.items():
                entry = next(e for e in c.query_updates.policy()["replacements"]
                             if e["measurement_query"].endswith(suffix))
                self.assertEqual(b.digest(output / rows[entry["query_id"]]["path"]), sha)
                if entry["original_query"] != entry["query_id"]:
                    self.assertNotIn(entry["original_query"], rows)

    def test_removed_sql_resolves_to_archive(self):
        for row in c.policy()["members"]:
            if row["role"] == "removed":
                resolved = resolve_sql_path("join", row["path"])
                self.assertEqual(b.digest(resolved), row["content_sha256"])


if __name__ == "__main__":
    unittest.main()
