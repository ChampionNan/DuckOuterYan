"""Pinned COUNT(*) replacements preserve everything except aggregate semantics."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import aggregate_count_refresh as refresh
import balanced_benchmark as b


def fixture(function="SUM"):
    variant = "grouped_" + function.lower()
    query = "aggregate__graph__fixture__sel_low__" + variant
    sql = ("-- original provenance\n"
           f"SELECT R2.dst AS group_key, {function}(R1.dst) AS value\n"
           "FROM (R1 R1 FULL OUTER JOIN R2 R2 ON R1.dst = R2.dst)\n"
           "WHERE R1.src <= 2\nGROUP BY R2.dst;\n")
    row = dict(query_id=query, path=f"graph/{query}.sql", family="graph", aggregate_variant=variant,
               aggregate_anchor="R1.dst", content_sha256=hashlib.sha256(sql.encode()).hexdigest(),
               sql_fingerprint=b.sql_fingerprint(sql, "graph"),
               expression_fingerprint=b.expression_key(sql, "graph"),
               qualification_status="PENDING_CPU9_MEASUREMENT", semantic_tier="low")
    pinned = {key: row[key] for key in refresh.PIN_FIELDS}
    spec = dict(revision="test-count", archive_revision="test-retired", expected_replacements=1,
                replacements=[pinned])
    return row, sql, spec


class AggregateCountRefreshTest(unittest.TestCase):
    def test_each_function_preserves_join_filter_grouping_and_new_identity(self):
        for function in ("MIN", "MAX", "SUM"):
            with self.subTest(function=function):
                row, sql, spec = fixture(function)
                original = copy.deepcopy(row)
                new, result = refresh.transform(row, sql, spec["replacements"][0], spec["revision"])
                self.assertEqual(row, original)
                self.assertEqual(result.split("\nFROM ", 1)[1], sql.split("\nFROM ", 1)[1])
                self.assertIn("SELECT R2.dst AS group_key, COUNT(*) AS row_count\n", result)
                self.assertEqual(new["aggregate_variant"], "grouped_count")
                self.assertEqual(new["aggregate_anchor"], "")
                self.assertEqual(new["replaces_query_id"], row["query_id"])
                self.assertEqual(new["replaces_content_sha256"], row["content_sha256"])
                self.assertEqual(new["expression_fingerprint"], row["expression_fingerprint"])
                self.assertNotEqual(new["sql_fingerprint"], row["sql_fingerprint"])
                self.assertEqual(Path(new["path"]).stem, new["query_id"])
                self.assertTrue(new["query_id"].endswith("__grouped_count"))
                self.assertEqual(new["qualification_status"], "PENDING_CPU9_MEASUREMENT")

    def test_rejects_changed_hash_and_metadata(self):
        row, sql, spec = fixture()
        with self.assertRaisesRegex(ValueError, "source hash changed"):
            refresh.transform(row, sql.replace("<= 2", "<= 3"), spec["replacements"][0], spec["revision"])
        row["family"] = "job"
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            refresh.transform(row, sql, spec["replacements"][0], spec["revision"])

    def test_does_not_rewrite_count_column_or_unsupported_expression(self):
        for expression in ("COUNT(R1.dst)", "SUM(R1.dst + 1)"):
            row, sql, spec = fixture()
            sql = sql.replace("SUM(R1.dst)", expression)
            row["content_sha256"] = hashlib.sha256(sql.encode()).hexdigest()
            row["sql_fingerprint"] = b.sql_fingerprint(sql, "graph")
            pinned = {k: row[k] for k in refresh.PIN_FIELDS}
            with self.assertRaisesRegex(ValueError, "simple column"):
                refresh.transform(row, sql, pinned, spec["revision"])

    def staged(self, directory):
        row, sql, spec = fixture()
        root = Path(directory)
        source = root / row["path"]
        source.parent.mkdir(parents=True)
        source.write_text(sql, encoding="utf-8")
        policy = root / "policy.json"
        policy.write_text(json.dumps(spec), encoding="utf-8")
        return row, sql, spec, root, policy

    def test_apply_and_validate_without_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, sql, spec, root, policy = self.staged(tmp)
            with patch.object(refresh, "POLICY", policy):
                updated = refresh.apply([row], root)
                self.assertFalse((root / row["path"]).exists())
                self.assertEqual(refresh.validate(root, updated), [row])
                self.assertEqual((root / refresh.QUERY_LIST).read_text(), updated[0]["path"] + "\n")
                self.assertEqual(json.loads((root / refresh.MARKER).read_text())["replaced_queries"], 1)

    def test_missing_target_refused_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, sql, spec, root, policy = self.staged(tmp)
            with patch.object(refresh, "POLICY", policy), self.assertRaisesRegex(ValueError, "missing"):
                refresh.apply([], root)
            self.assertEqual((root / row["path"]).read_text(), sql)

    def test_duplicate_new_identity_or_fingerprint_refused(self):
        for field in ("query_id", "path", "sql_fingerprint"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                row, sql, spec, root, policy = self.staged(tmp)
                new, _ = refresh.transform(row, sql, spec["replacements"][0], spec["revision"])
                other = dict(new, query_id="unrelated", path="graph/unrelated.sql", sql_fingerprint="unrelated")
                other[field] = new[field]
                with patch.object(refresh, "POLICY", policy), self.assertRaisesRegex(ValueError, "Duplicate"):
                    refresh.apply([row, other], root)
                self.assertEqual((root / row["path"]).read_text(), sql)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, sql, spec, root, policy = self.staged(tmp)
            new, _ = refresh.transform(row, sql, spec["replacements"][0], spec["revision"])
            (root / new["path"]).write_text("user file", encoding="utf-8")
            with patch.object(refresh, "POLICY", policy), self.assertRaisesRegex(ValueError, "already exists"):
                refresh.apply([row], root)
            self.assertEqual((root / new["path"]).read_text(), "user file")
            self.assertEqual((root / row["path"]).read_text(), sql)

    def test_editing_sql_and_its_manifest_hash_does_not_bypass_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, sql, spec, root, policy = self.staged(tmp)
            with patch.object(refresh, "POLICY", policy):
                updated = refresh.apply([row], root)
                path = root / updated[0]["path"]
                altered = path.read_text().replace("<= 2", "<= 3")
                path.write_text(altered, encoding="utf-8")
                updated[0]["content_sha256"] = hashlib.sha256(altered.encode()).hexdigest()
                updated[0]["sql_fingerprint"] = b.sql_fingerprint(altered, "graph")
                with self.assertRaisesRegex(ValueError, "source hash changed"):
                    refresh.validate(root, updated)

    def test_policy_and_query_list_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            row, sql, spec, root, policy = self.staged(tmp)
            with patch.object(refresh, "POLICY", policy):
                updated = refresh.apply([row], root)
                (root / refresh.QUERY_LIST).write_text("wrong.sql\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "query list changed"):
                    refresh.validate(root, updated)
                spec["revision"] = "different"
                policy.write_text(json.dumps(spec), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "policy changed"):
                    refresh.validate(root, updated)


if __name__ == "__main__":
    unittest.main()
