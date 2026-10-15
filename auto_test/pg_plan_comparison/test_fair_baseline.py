"""Tests for evidence failures that would invalidate a shared PG-tree baseline."""

import copy
import unittest

from fair_baseline import query_sha256, verify_shared_baseline


def scan(name):
    return {"op": "scan", "relation": name}


def join(kind, left, right):
    return {"op": "join", "join_type": kind, "left": left, "right": right}


class SharedBaselineTests(unittest.TestCase):
    sql = "SELECT a.id FROM a LEFT JOIN (b INNER JOIN c ON b.id=c.id) ON a.id=b.id"

    def setUp(self):
        self.pg = join("left", scan("a"), join("inner", scan("b"), scan("c")))

    def verify(self, native=None, **overrides):
        arguments = dict(sql=self.sql, pg_query_sha256=query_sha256(self.sql),
                         native_query_sha256=query_sha256(self.sql))
        arguments.update(overrides)
        return verify_shared_baseline(self.pg, native or self.pg, ["a", "b", "c"], **arguments)

    def test_legal_child_swaps_keep_preserved_side_and_share_one_measurement(self):
        swapped = join("right", join("inner", scan("c"), scan("b")), scan("a"))
        result = self.verify(swapped, profile_tree=swapped, profile_sql=self.sql + ";\n")
        self.assertEqual(result["status"], "verified_shared_native_realization")
        self.assertTrue(result["native_profile_verified"])
        self.assertFalse(result["independent_pg_replay_measurement"])
        self.assertEqual(result["measurement_policy"], "measure_native_once_and_label_as_shared")

    def test_rejects_preserved_side_mismatch(self):
        wrong = join("left", join("inner", scan("b"), scan("c")), scan("a"))
        with self.assertRaisesRegex(ValueError, "typed join-tree mismatch"):
            self.verify(wrong)

    def test_rejects_join_type_mismatch_even_with_equal_grouping(self):
        wrong = copy.deepcopy(self.pg)
        wrong["join_type"] = "full"
        with self.assertRaisesRegex(ValueError, "typed join-tree mismatch"):
            self.verify(wrong)

    def test_rejects_grouping_mismatch_even_with_same_tables(self):
        wrong = join("left", join("inner", scan("a"), scan("b")), scan("c"))
        with self.assertRaisesRegex(ValueError, "typed join-tree mismatch"):
            self.verify(wrong)

    def test_rejects_duplicate_leaves_instead_of_collapsing_to_a_set(self):
        wrong = join("left", scan("a"), join("inner", scan("b"), scan("b")))
        with self.assertRaisesRegex(ValueError, "duplicate base-table"):
            self.verify(wrong)

    def test_rejects_table_count_and_identity_mismatch(self):
        with self.assertRaisesRegex(ValueError, "base-table count"):
            self.verify(join("left", scan("a"), scan("b")))
        wrong = join("left", scan("a"), join("inner", scan("b"), scan("d")))
        with self.assertRaisesRegex(ValueError, "base-table identities"):
            self.verify(wrong)

    def test_four_distinct_tables_and_full_child_swap_are_supported(self):
        original = join("full", self.pg, scan("d"))
        swapped = join("full", scan("d"), self.pg)
        sql = ("SELECT a.id FROM (a LEFT JOIN (b INNER JOIN c ON b.id=c.id) "
               "ON a.id=b.id) FULL JOIN d ON a.id=d.id")
        digest = query_sha256(sql)
        result = verify_shared_baseline(original, swapped, ["a", "b", "c", "d"], sql=sql,
                                        pg_query_sha256=digest, native_query_sha256=digest)
        self.assertEqual(result["relation_count"], 4)

    def test_query_identity_and_bare_profile_identity_are_required(self):
        for key in ("pg_query_sha256", "native_query_sha256"):
            with self.assertRaisesRegex(ValueError, "query identity mismatch"):
                self.verify(**{key: query_sha256(self.sql + " WHERE a.id=1")})
        with self.assertRaisesRegex(ValueError, "query identity mismatch"):
            self.verify(profile_tree=self.pg, profile_sql=self.sql + " WHERE a.id=1")
        with self.assertRaisesRegex(ValueError, "bare SELECT"):
            self.verify(profile_tree=self.pg, profile_sql="EXPLAIN " + self.sql)

    def test_profile_is_checked_not_just_the_explain(self):
        wrong = copy.deepcopy(self.pg)
        wrong["join_type"] = "inner"
        with self.assertRaisesRegex(ValueError, "typed join-tree mismatch"):
            self.verify(profile_tree=wrong, profile_sql=self.sql)
        with self.assertRaisesRegex(ValueError, "supplied together"):
            self.verify(profile_tree=self.pg)

    def test_rejects_ambiguous_occurrences_schemas_and_hidden_subtrees(self):
        for change in ({"occurrence": 1}, {"occurrence": True}, {"schema": "other"},
                       {"children": [scan("d")]}, {"right": scan("d")}):
            wrong = copy.deepcopy(self.pg)
            wrong["left"].update(change)
            with self.assertRaises(ValueError):
                self.verify(wrong)

    def test_hash_preserves_internal_sql_and_rejects_scripts(self):
        self.assertEqual(query_sha256(self.sql), query_sha256("\r\n" + self.sql + "; \r\n"))
        self.assertNotEqual(query_sha256(self.sql), query_sha256(self.sql.replace("a.id", "a.x")))
        for bad in (self.sql + "; SELECT 2", "EXPLAIN " + self.sql, self.sql + " -- comment"):
            with self.assertRaises(ValueError):
                query_sha256(bad)


if __name__ == "__main__":
    unittest.main()
