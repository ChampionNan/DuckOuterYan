#!/usr/bin/env python3
"""Frozen source, predicate placement and provenance checks for the isolated pilot."""
import hashlib
import unittest

from benchmark_corpus import count_base_relations
from prepare_custdist_retest import ACTIVE, QUERY, SOURCE_SHA, prepare


class CustdistPilotTest(unittest.TestCase):
    def test_reproducible_and_scoped(self):
        entries = prepare()
        self.assertEqual(entries, prepare())
        self.assertEqual(len(entries), 6)
        source = (ACTIVE / "tpch" / (QUERY + ".sql")).read_text()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), SOURCE_SHA)
        for row, sql in entries:
            self.assertEqual(count_base_relations(sql), 4)
            self.assertEqual(row["content_sha256"], hashlib.sha256(sql.encode()).hexdigest())
            self.assertEqual(row["pilot_source_sha256"], SOURCE_SHA)
            self.assertEqual(sql.count("WHERE " + row["selectivity_predicate"]), 1)
            self.assertEqual(row["join_vector"], "LRF")
            if row["pilot_placement"] == "input":
                scan = "(SELECT * FROM orders WHERE {}) AS orders".format(
                    row["selectivity_predicate"].replace("orders.", ""))
                original = next(s for r, s in entries if r["pilot_days"] == row["pilot_days"]
                                and r["pilot_placement"] == "where")
                self.assertEqual(sql.replace("LEFT OUTER JOIN " + scan + " ON",
                                             "LEFT OUTER JOIN orders   ON"), original)
            if row["pilot_role"] == "original_control":
                self.assertEqual(sql, source)


if __name__ == "__main__":
    unittest.main()
