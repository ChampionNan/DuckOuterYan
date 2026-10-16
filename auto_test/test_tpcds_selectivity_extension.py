"""Historical selection produces new audited cohorts, never measured results."""
from collections import Counter
import contextlib
import copy
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import balanced_benchmark as b
import benchmark_speedup_screen as screen
import benchmark_retirements as retirements
from benchmark_corpus import count_base_relations, historical_manifests, resolve_sql_path
import tpcds_refresh as refresh
import tpcds_selectivity_extension as extension
import benchmark_plan_cohort as cohort
import graph_dataset_extension
import graph_dataset_promotion
from test_gen_outerjoin_benchmark import forbid_result_access


class TPCDSSelectivityExtensionTest(unittest.TestCase):
    def test_historical_threshold_uses_complete_unrounded_timings(self):
        evidence = dict(historical_correct="TRUE", historical_selected="1", historical_timing_status="measured",
                        historical_duckdb_s="0.9", historical_outeryan_s="1", historical_speedup="0")
        self.assertTrue(extension.historical_eligible(evidence, .9))
        for change in (dict(historical_duckdb_s="0.899999999"), dict(historical_duckdb_s="nan"),
                       dict(historical_duckdb_s="0"), dict(historical_duckdb_s="NA"),
                       dict(historical_outeryan_s="inf"), dict(historical_outeryan_s="-1"),
                       dict(historical_correct="NOT-CHECKED"), dict(historical_correct="FALSE"),
                       dict(historical_selected="0"), dict(historical_timing_status="fallback-skip")):
            with self.subTest(change=change):
                self.assertFalse(extension.historical_eligible(dict(evidence, **change), .9))

    def original_rows(self):
        corpus = cohort.input_corpus()
        rows = b.read_manifest(corpus / "manifest.csv")
        rows, _ = graph_dataset_extension.validate(corpus, rows)
        rows, _ = graph_dataset_promotion.validate(corpus, rows)
        return [r for r in rows if not extension.is_extension(r)]

    def test_old_recovery_builder_is_unchanged(self):
        recorded = {r["query_id"]: r for r in self.original_rows()
                    + b.read_manifest(b.ROOT / "benchmark/speedup_excluded.csv")}
        with forbid_result_access():
            candidates = list(refresh.recovery_queries())
        for row, sql in candidates:
            old = recorded[row["query_id"]]
            self.assertTrue(all(str(old.get(key, "")) == str(value) for key, value in row.items()))
            self.assertEqual(b.sql_fingerprint(sql, "tpcds"), old["sql_fingerprint"])

    def test_new_patterns_have_three_real_calibrated_cohorts(self):
        spec = extension.policy()
        with forbid_result_access():
            additions = list(extension.extension_queries())
        self.assertEqual(len(additions), spec["expected_new_candidates"])
        self.assertEqual(Counter((r["extension_template"], r["semantic_tier"]) for r, _ in additions),
                         {(t["name"], tier): 1 for t in spec["templates"] for tier in b.TIERS})
        original = {r["sql_fingerprint"] for r in self.original_rows()}
        fingerprints = {r["sql_fingerprint"] for r, _ in additions}
        self.assertEqual(len(fingerprints), len(additions))
        self.assertTrue(fingerprints.isdisjoint(original | extension.excluded_fingerprints()))
        for row, sql in additions:
            self.assertEqual(row["evaluation_role"], extension.ROLE)
            self.assertEqual(row["qualification_status"], "PENDING_CPU9_MEASUREMENT")
            self.assertEqual(row["qualification_min_speedup"], .5)
            self.assertNotIn("tm_off", row)
            self.assertNotIn("tm_on", row)
            self.assertNotIn("historical_speedup", row)
            self.assertEqual(count_base_relations(sql), int(row["relation_count"]))
            self.assertEqual(b.expression_key(sql, "tpcds"), row["expression_fingerprint"])
            self.assertIn(row["selectivity_predicate"], sql)
            self.assertEqual(row["calibration_in_range"], "true")
            self.assertLessEqual(float(row["target_max_fraction"]), .6)
            self.assertIn("CPU9 audit required", row["parameter_policy"])

    def test_replacement_preserves_nine_sql_and_does_not_inherit_old_timings(self):
        spec = extension.policy()
        previous_path = b.ROOT / spec["previous_policy"]
        self.assertEqual(b.digest(previous_path), spec["previous_policy_sha256"])
        previous = json.loads(previous_path.read_text())
        previous_candidates = {row["query_id"]: (row, sql)
                               for row, sql in extension.extension_queries(previous)}
        retained, replaced = [], []
        for row, sql in extension.extension_queries():
            if row["query_id"] in previous_candidates:
                self.assertEqual((row, sql), previous_candidates[row["query_id"]])
                retained.append(row)
            else:
                replaced.append(row)
                self.assertEqual(row["provenance_class"], "source_connected_subgraph")
                self.assertFalse(any(key.startswith("historical_") for key in row))
                self.assertIn("extension_20261008_r2", row["query_id"])
        self.assertEqual(len(retained), 9)
        self.assertEqual(len(replaced), 6)
        retired = {r["query_id"] for r in spec["retired_queries"]}
        self.assertEqual(retired, set(previous_candidates) - {r["query_id"] for r in retained})
        self.assertEqual(Counter(r["retirement_reason"] for r in spec["retired_queries"]),
                         dict(observed_dual_engine_timeout=3,
                              same_item_only_fact_fact_fanout_risk_not_yet_measured=3))

    def test_replacements_use_connected_single_fact_source_edges_and_mixed_joins(self):
        spec = extension.policy()
        templates = {t["name"]: t for t in spec["templates"]}
        for row, sql in extension.extension_queries():
            if row["provenance_class"] != "source_connected_subgraph":
                continue
            template = templates[row["extension_template"]]
            source = (b.legacy.REPO_ROOT / template["source_location"]).read_text()
            def edges(text):
                return {tuple(sorted((m.group(1).lower(), m.group(2).lower())))
                        for m in b.legacy.SIMPLE_EDGE_EQUALITY.finditer(text)}
            self.assertTrue(edges(sql) <= edges(source))
            graph = b.legacy.sql_join_graph(sql)
            aliases = {alias for edge in graph for alias in edge}
            self.assertEqual(len(aliases), int(row["relation_count"]))
            self.assertEqual(sum(graph.values()), len(aliases) - 1)
            reached = {next(iter(aliases))}
            for _ in aliases:
                reached |= {v for edge in graph if reached.intersection(edge) for v in edge}
            self.assertEqual(reached, aliases)
            facts = re.findall(r"\b(?:store_sales|web_sales|catalog_sales|store_returns|web_returns|catalog_returns)\b",
                               b.body(sql), re.I)
            self.assertEqual(facts, ["web_sales"])
            self.assertEqual(b.legacy.sql_join_kind_counts(sql), Counter(row["join_vector"]))
            self.assertGreater(len(set(row["join_vector"])), 1)

    def test_exact_retirement_archive_is_recoverable_and_rejects_local_edits(self):
        spec = extension.policy()
        previous = json.loads((b.ROOT / spec["previous_policy"]).read_text())
        retired_ids = {r["query_id"] for r in spec["retired_queries"]}
        retired = [(r, sql) for r, sql in extension.extension_queries(previous) if r["query_id"] in retired_ids]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "benchmark"
            (corpus / "tpcds").mkdir(parents=True)
            for row, sql in retired:
                (corpus / row["path"]).write_text(sql)
            old_rows = [r for r, _ in retired]
            extension.archive_retired(corpus, old_rows, root)
            archive = root / "revisions" / spec["retirement_revision"] / "benchmark"
            self.assertEqual(len(b.read_manifest(archive / "manifest.csv")), 6)
            self.assertIn((None, archive / "manifest.csv"), list(historical_manifests(root)))
            for row, sql in retired:
                self.assertEqual((archive / row["path"]).read_text(), sql)
                # Removing the active copy must leave report-time source lookup working.
                (corpus / row["path"]).unlink()
                self.assertEqual(resolve_sql_path(row["query_class"], row["path"], root), archive / row["path"])
            (corpus / retired[0][0]["path"]).write_text("SELECT 1;\n")
            with self.assertRaisesRegex(ValueError, "locally edited"):
                extension.archive_retired(corpus, old_rows, root)

    def test_overlay_preserves_every_existing_row_and_validates_its_list(self):
        records = self.original_rows() + retirements.archived_rows()[0]
        before = copy.deepcopy(records)
        with tempfile.TemporaryDirectory() as tmp, forbid_result_access():
            output = Path(tmp)
            (output / "tpcds").mkdir()
            retained = extension.apply(records, output)
            self.assertEqual(records, before)
            self.assertEqual(retained[:len(records)], before)
            self.assertEqual(extension.validate(output, retained), before)
            self.assertEqual(Counter(r["family"] for r in retained), extension.policy()["expected_counts_after"])
            (output / extension.QUERY_LIST).write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "query list changed"):
                extension.validate(output, retained)

    def test_new_name_cannot_alias_existing_or_excluded_sql(self):
        records = self.original_rows() + retirements.archived_rows()[0]
        additions = list(extension.extension_queries())
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "tpcds").mkdir()
            duplicate = copy.deepcopy(additions)
            duplicate[0][0]["sql_fingerprint"] = records[0]["sql_fingerprint"]
            with mock.patch.object(extension, "extension_queries", return_value=iter(duplicate)):
                with self.assertRaisesRegex(ValueError, "Duplicate or excluded"):
                    extension.apply(records, output)
            rejected = {additions[0][0]["sql_fingerprint"]}
            with mock.patch.object(extension, "excluded_fingerprints", return_value=rejected):
                with self.assertRaisesRegex(ValueError, "Duplicate or excluded"):
                    extension.apply(records, output)
            self.assertEqual(list((output / "tpcds").glob("*.sql")), [])

    def test_invalid_policy_fails_before_generation(self):
        original = extension.policy()
        variants = []
        incomplete = copy.deepcopy(original)
        incomplete["expected_new_candidates"] += 1
        variants.append((incomplete, "three-tier"))
        unsafe = copy.deepcopy(original)
        unsafe["templates"][0]["archive_sql"] = "../outside.sql"
        variants.append((unsafe, "Unsafe"))
        repeated = copy.deepcopy(original)
        repeated["templates"][0]["expression_fingerprint"] = refresh.policy()["templates"][0]["expression_fingerprint"]
        repeated["templates"][0]["aggregate_variant"] = refresh.policy()["templates"][0]["aggregate_variant"]
        variants.append((repeated, "existing historical pattern"))
        counts = copy.deepcopy(original)
        counts["expected_counts_after"]["graph"] += 1
        variants.append((counts, "counts"))
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "policy.json"
            for spec, message in variants:
                with self.subTest(message=message):
                    b.write_json(source, spec)
                    with mock.patch.object(extension, "POLICY", source):
                        with self.assertRaisesRegex(ValueError, message):
                            extension.policy()



    def test_regeneration_preserves_screened_sql_and_never_reads_results(self):
        corpus = b.ROOT / "benchmark"
        original = [r for r in b.read_manifest(corpus / "manifest.csv") if not extension.is_extension(r)]
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), forbid_result_access():
            root = Path(tmp)
            b.generate(root)
            generated = root / "benchmark"
            manifest = (generated / "manifest.csv").read_bytes()
            self.assertEqual(manifest, (corpus / "manifest.csv").read_bytes())
            for row in original:
                self.assertEqual((generated / row["path"]).read_bytes(), (corpus / row["path"]).read_bytes())
            import benchmark_retirements
            # Validate this earlier transformation against its complete input,
            # before the subsequent graph promotions and plan-cohort selection.
            predecessor = cohort.input_corpus()
            restored = b.validate(predecessor)
            restored, _ = graph_dataset_extension.validate(predecessor, restored)
            restored, _ = graph_dataset_promotion.validate(predecessor, restored)
            restored, _ = benchmark_retirements.validate(predecessor, restored)
            before = extension.validate(predecessor, restored)
            historical_original = self.original_rows()
            self.assertEqual([r for r in before if r["query_id"] in {x["query_id"] for x in historical_original}],
                             historical_original)
            self.assertEqual(len(before), sum(screen.policy()["expected_counts_after"].values()))
            b.generate(root)
            self.assertEqual(manifest, (generated / "manifest.csv").read_bytes())


if __name__ == "__main__":
    unittest.main()
