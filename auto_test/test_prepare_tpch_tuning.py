"""Structural guards for SQL-only, count-preserving TPC-H tuning proposals."""
import json
import unittest

import balanced_benchmark as b
import prepare_tpch_tuning as tuning


class TpchQueryTuningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(tuning.POLICY.read_text())
        cls.rows = b.read_manifest(tuning.ACTIVE / "manifest.csv")
        cls.by_id = {r["query_id"]: r for r in cls.rows}

    def test_exact_scope_and_frozen_active_manifest(self):
        self.assertEqual(len(self.rows), 720)
        self.assertEqual(b.digest(tuning.ACTIVE / "manifest.csv"), self.spec["active_manifest_sha256"])
        self.assertEqual(len(self.spec["replacements"]), 31)
        selected = self.spec["reference_selected_queries"]
        self.assertEqual(len(selected), len(set(selected)))
        self.assertEqual(len(selected), 281)
        self.assertEqual(sum(self.by_id[q]["family"] == "tpch" for q in selected), 80)
        for pin in self.spec["replacements"]:
            row = self.by_id[pin["original"]["query_id"]]
            self.assertEqual(row["family"], "tpch")
            self.assertIn(row["query_id"], selected)
            self.assertEqual(b.digest(tuning.ACTIVE / row["path"]), pin["original"]["content_sha256"])

    def test_preserve_projection_grouping_relations_and_source_edges(self):
        for pin in self.spec["replacements"]:
            row = self.by_id[pin["original"]["query_id"]]
            original = b.body((tuning.ACTIVE / row["path"]).read_text())
            sql, predicate = tuning.replacement_sql(pin, self.rows)
            with self.subTest(query=row["query_id"]):
                self.assertEqual(original.split("FROM", 1)[0], sql.split("FROM", 1)[0])
                self.assertEqual(original.split("GROUP BY")[-1].strip() if "GROUP BY" in original else "",
                                 sql.split("GROUP BY")[-1].strip() if "GROUP BY" in sql else "")
                self.assertEqual(tuning.equalities(original), tuning.equalities(sql))
                self.assertEqual(tuning.count_base_relations(sql), int(row["relation_count"]))
                self.assertGreaterEqual(len(set(tuning.JOIN.findall(sql))), 2)
                self.assertNotEqual(b.sql_fingerprint(original, "tpch"), b.sql_fingerprint(sql, "tpch"))
                self.assertIn(predicate, sql)

    def test_filter_only_cases_do_not_change_patterns(self):
        pins = [p for p in self.spec["replacements"] if p["rule"] == "selectivity_only"]
        self.assertEqual(len(pins), 14)
        for pin in pins:
            row = self.by_id[pin["original"]["query_id"]]
            original = (tuning.ACTIVE / row["path"]).read_text()
            sql, _ = tuning.replacement_sql(pin, self.rows)
            self.assertEqual(tuning.from_expression(original), tuning.from_expression(sql))

    def test_unknown_rule_rejected(self):
        pin = dict(self.spec["replacements"][0], rule="silently_change_all_families")
        with self.assertRaisesRegex(ValueError, "Unknown"):
            tuning.replacement_sql(pin, self.rows)

    def test_no_duplicate_proposed_sql(self):
        seen = {r["sql_fingerprint"] for r in self.rows}
        for pin in self.spec["replacements"]:
            sql, _ = tuning.replacement_sql(pin, self.rows)
            fp = b.sql_fingerprint(sql, "tpch")
            self.assertNotIn(fp, seen)
            seen.add(fp)


if __name__ == "__main__":
    unittest.main()
