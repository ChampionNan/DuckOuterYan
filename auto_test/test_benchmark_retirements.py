"""Final-stage query removals must be exact, recoverable and repeatable."""
from collections import Counter
from pathlib import Path
import tempfile
import unittest

import balanced_benchmark as b
import benchmark_retirements as r
from benchmark_corpus import resolve_sql_path
from benchmark_speedup_screen import below_threshold


class BenchmarkRetirementsTest(unittest.TestCase):
    def test_inclusive_boundary_uses_unrounded_times(self):
        row = dict(correct="NOT-CHECKED", correctness_check="disabled", timing_status="measured", tm_off="0.6", tm_on="1")
        self.assertTrue(below_threshold(row, .6, inclusive=True, allow_unchecked=True))
        self.assertFalse(below_threshold(dict(row, tm_off="0.600000001"), .6, inclusive=True, allow_unchecked=True))
        for change in (dict(timing_status="timeout"), dict(tm_on="nan"), dict(correct="FALSE")):
            self.assertFalse(below_threshold(dict(row, **change), .6, inclusive=True, allow_unchecked=True))

    def test_exact_removals_archive_and_lists(self):
        rows = b.validate(b.ROOT / "benchmark")
        archived, paths = r.archived_rows()
        self.assertEqual(len(rows), 724)
        self.assertEqual(Counter(x["family"] for x in archived), dict(graph=1, tpch=3, tpcds=3, job=2))
        for row in archived:
            self.assertFalse((b.ROOT / "benchmark" / row["path"]).exists())
            self.assertEqual(resolve_sql_path(row["query_class"], row["path"]), paths[row["path"]])
        self.assertEqual(len((b.ROOT / "benchmark/aggregate_count_refresh.txt").read_text().splitlines()), 33)
        ids = {x["query_id"] for x in rows}
        self.assertIn("aggregate__job__job_10a_cast_credits__right_deep__rlif__87f83502__sel_medium__grouped_count", ids)

    def test_changed_marker_or_stale_list_rejected(self):
        rows = b.read_manifest(b.ROOT / "benchmark/manifest.csv")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            marker = r.marker(r.policy())
            b.write_json(output / r.MARKER, marker)
            r.validate(output, rows)
            (output / "selected.txt").write_text(r.policy()["excluded"][0]["path"] + "\n")
            with self.assertRaisesRegex(ValueError, "query list"):
                r.validate(output, rows)
            (output / "selected.txt").unlink()
            marker["removed_queries"] = 0
            b.write_json(output / r.MARKER, marker)
            with self.assertRaisesRegex(ValueError, "policy changed"):
                r.validate(output, rows)


if __name__ == "__main__":
    unittest.main()
