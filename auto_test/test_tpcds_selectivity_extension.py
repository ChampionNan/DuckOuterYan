"""Historical selection produces new audited cohorts, never measured results."""
from collections import Counter
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import balanced_benchmark as b
import benchmark_speedup_screen as screen
from benchmark_corpus import count_base_relations
import qualify_benchmark as q
import tpcds_refresh as refresh
import tpcds_selectivity_extension as extension
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
        return [r for r in b.read_manifest(b.ROOT / "benchmark/manifest.csv")
                if not extension.is_extension(r)]

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

    def test_overlay_preserves_every_existing_row_and_validates_its_list(self):
        records = self.original_rows()
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
        records = self.original_rows()
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

    def test_extension_still_requires_current_sql_and_selectivity_evidence(self):
        candidate, _ = next(extension.extension_queries())
        candidate = {key: str(value) for key, value in candidate.items()}
        audit = dict(execution_host="cpu9", manifest_sha256="manifest", design_sha256=b.digest(b.DESIGN),
                     profiles=[dict(profile=candidate["selectivity_profile"], tier=candidate["semantic_tier"],
                                    in_range=True, database_signature="db")])
        result = dict(corpus_revision=b.REVISION, sql_content_sha256=candidate["content_sha256"],
                      corpus_manifest_sha256="manifest", execution_host="cpu9", database_signature="db",
                      timeout_seconds="600", timing_status="measured", correct="TRUE", tm_off="1", tm_on="1")
        self.assertEqual(q.classify(candidate, None, audit, "manifest"), "pending_measurement")
        self.assertEqual(q.classify(candidate, result, None, "manifest"), "selectivity_audit_missing")
        self.assertEqual(q.classify(candidate, dict(result, sql_content_sha256="old"), audit, "manifest"),
                         "sql_or_revision_mismatch")
        self.assertEqual(q.classify(candidate, result, audit, "manifest"), "eligible")
        audit["profiles"][0]["in_range"] = False
        self.assertEqual(q.classify(candidate, result, audit, "manifest"), "selectivity_unverified_or_out_of_band")

    def test_extension_profiles_use_the_normal_three_band_audit(self):
        additions = [r for r, _ in extension.extension_queries()]
        design = b.load_design()
        profiles = {row["selectivity_profile"] for row in additions}

        def run_count(command, **kwargs):
            sql = command[-1]
            profile = next(design["profiles"][name] for name in profiles
                           if sql.endswith(" FROM " + design["profiles"][name]["calibration_from"] + ";"))
            calibration = profile["calibration"]
            counts = dict(n=calibration["n"], **{f"c{i}": count for i, count in
                                               enumerate(calibration["qualified_rows"])})
            self.assertIn("SET disabled_optimizers='outer_yan'", sql)
            self.assertIn("-readonly", command)
            return mock.Mock(stdout=json.dumps([counts]))

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(b, "validate", return_value=additions), \
                mock.patch.object(q, "database_signature", return_value="db"), \
                mock.patch.object(q.subprocess, "run", side_effect=run_count) as run:
            output = Path(tmp) / "audit.json"
            self.assertTrue(q.audit_selectivity(b.ROOT, Path("duckdb"), output, 10))
            audit = json.loads(output.read_text())
            self.assertEqual(run.call_count, len(profiles))
            self.assertEqual({(p["profile"], p["tier"]) for p in audit["profiles"]},
                             {(profile, tier) for profile in profiles for tier in b.TIERS})
            self.assertTrue(all(p["in_range"] for p in audit["profiles"]))
            self.assertEqual(audit["historical_cases_outside_band_audit"], [])

    def test_regeneration_preserves_screened_sql_and_never_reads_results(self):
        original = self.original_rows()
        corpus = b.ROOT / "benchmark"
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), forbid_result_access():
            root = Path(tmp)
            b.generate(root)
            generated = root / "benchmark"
            manifest = (generated / "manifest.csv").read_bytes()
            self.assertEqual(manifest, (corpus / "manifest.csv").read_bytes())
            for row in original:
                self.assertEqual((generated / row["path"]).read_bytes(), (corpus / row["path"]).read_bytes())
            before = extension.validate(generated, b.validate(generated))
            self.assertEqual(before, original)
            self.assertEqual(len(before), sum(screen.policy()["expected_counts_after"].values()))
            b.generate(root)
            self.assertEqual(manifest, (generated / "manifest.csv").read_bytes())


if __name__ == "__main__":
    unittest.main()
