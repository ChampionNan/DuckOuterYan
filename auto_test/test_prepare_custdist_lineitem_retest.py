#!/usr/bin/env python3
import hashlib
from pathlib import Path
import tempfile
import unittest

from benchmark_corpus import count_base_relations
from prepare_custdist_lineitem_retest import entries, materialize
from prepare_custdist_retest import prepare as previous_entries


class LineitemPilotTest(unittest.TestCase):
    def test_sql_scope(self):
        data = entries()
        self.assertEqual(data, entries())
        control = next(s for r, s in previous_entries()
                       if r["pilot_days"] == "840" and r["pilot_placement"] == "input")
        self.assertEqual(data[0][1], control)
        for row, sql in data:
            self.assertEqual(count_base_relations(sql), 4)
            self.assertEqual(row["join_vector"], "LRF")
            self.assertEqual(hashlib.sha256(sql.encode()).hexdigest(), row["content_sha256"])
            self.assertEqual(sql.count("WHERE " + row["selectivity_predicate"]), 1)
            predicate = row["lineitem_selectivity_predicate"]
            if predicate:
                self.assertEqual(row["equivalent_to_active"], "false")
                leaf = "(SELECT * FROM lineitem WHERE {}) AS lineitem".format(
                    predicate.replace("lineitem.", ""))
                restored = sql.replace("RIGHT OUTER JOIN " + leaf + " ON", "RIGHT OUTER JOIN lineitem ON")
                restored = restored.replace("\n  AND " + predicate, "")
                self.assertEqual(restored[restored.index("SELECT *"):].rstrip(),
                                 control[control.index("SELECT *"):].rstrip())

    def test_frozen_corpus_is_reproducible(self):
        frozen = Path(__file__).parent / "outerjoin_benchmark/candidates/custdist_lineitem_20261015"
        with tempfile.TemporaryDirectory(prefix="custdist-line-regen-") as tmp:
            generated = Path(tmp) / "corpus"
            materialize(generated)
            for file in generated.rglob("*"):
                if file.is_file():
                    self.assertEqual(file.read_bytes(), (frozen / file.relative_to(generated)).read_bytes())


if __name__ == "__main__":
    unittest.main()
