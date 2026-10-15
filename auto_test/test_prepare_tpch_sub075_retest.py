"""Reproducible and scoped query-only pilots; preserve outer-join semantics."""
from collections import Counter
import hashlib
from pathlib import Path
import tempfile
import unittest

from benchmark_corpus import count_base_relations, read_manifest
import prepare_tpch_sub075_retest as pilot


class Sub075Test(unittest.TestCase):
    def test_identity_scope_and_predicate_placement(self):
        data = pilot.entries()
        self.assertEqual(data, pilot.entries())
        self.assertEqual(Counter(r["pilot_short_id"] for r, _ in data),
                         {"Q-H-LD-36": 7, "A-H-RD-10": 7, "A-H-RD-11": 7})
        self.assertEqual(sum(r["pilot_run_group"] == "sf50_shortlist" for r, _ in data), 12)
        original = {r["query_id"]: r for r in read_manifest(pilot.SOURCE / "manifest.csv")}
        for row, sql in data:
            old = original[row["pilot_source_query"]]
            self.assertEqual(row["content_sha256"], hashlib.sha256(sql.encode()).hexdigest())
            self.assertEqual(count_base_relations(sql), int(old["relation_count"]))
            for key in ("tree_shape", "join_vector", "source_seed", "aggregate_variant"):
                self.assertEqual(row[key], old[key])
            self.assertIn("__sel_" + row["semantic_tier"] + "__", row["query_id"])
            self.assertEqual(sql.count("WHERE " + row["selectivity_predicate"]), 1)
            if row["pilot_variant"].startswith("input"):
                leaf = "(SELECT * FROM {} WHERE {}) {}".format(
                    row["pilot_table"], row["selectivity_predicate"].replace(row["pilot_alias"] + ".", ""), row["pilot_alias"])
                self.assertEqual(sql.count(leaf), 1)
                sql = sql.replace(leaf, row["pilot_table"] + " " + row["pilot_alias"], 1)
            sql = sql.replace(row["selectivity_predicate"], old["selectivity_predicate"], 1)
            sql = sql.replace("-- selectivity: " + row["semantic_tier"] + ";",
                              "-- selectivity: " + old["semantic_tier"] + ";", 1)
            self.assertEqual(sql, (pilot.SOURCE / old["path"]).read_text())

    def test_frozen_corpus_and_launcher(self):
        frozen = Path(__file__).parent / "outerjoin_benchmark/candidates/tpch_sub075_20261015"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pilot"
            pilot.materialize(output)
            for path in output.rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (frozen / path.relative_to(output)).read_bytes())
            with self.assertRaises(FileExistsError):
                pilot.materialize(output)
        shell = Path(__file__).with_name("run_tpch_sub075_retest.sh").read_text()
        for option in ('--threads 32 --runs 5 --timeout 600', '--no-check-correctness', '--sf 50'):
            self.assertIn(option, shell)
        self.assertIn('pgrep -x duckdb', shell)
        self.assertIn('--input-followup', shell)
        self.assertIn("r['short_query'] == 'A-H-RD-11'", shell)
        self.assertIn("r['variant'] in ('input_d480', 'input_d240')", shell)


if __name__ == "__main__":
    unittest.main()
