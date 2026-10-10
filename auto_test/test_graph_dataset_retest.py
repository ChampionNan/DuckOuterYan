"""No long-running queries: verify the exact graph dataset replacement cohort."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from benchmark_corpus import read_manifest, count_base_relations
import prepare_graph_dataset_retest as retest


def audit_fixture(spec):
    design = json.loads(retest.DESIGN.read_text())
    profiles = {}
    values = {"anchor/low": (118, 15147), "anchor/medium": (2177, 152647),
              "auxiliary/low": (539, 45801), "auxiliary/medium": (824, 76447)}
    for role, name in (("anchor", "graph_source_range"), ("auxiliary", "graph_aux_source_range")):
        for tier in ("low", "medium"):
            threshold, n = values[role + "/" + tier]
            bands = design["profiles"][name].get("tiers", design["tiers"])
            profiles[role + "/" + tier] = dict(threshold=threshold, qualified_rows=n,
                total_rows=508837, observed_fraction=n/508837,
                band=next(b for b in bands if b["name"] == tier))
    return dict(profiles=profiles, dataset="epinions")


class GraphDatasetRetestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = retest.load_policy()
        cls.corpus = retest.ROOT / "benchmark"
        if (cls.corpus / "graph_dataset_promotion.json").exists():
            import graph_dataset_promotion
            cls.corpus = graph_dataset_promotion.ARCHIVE
        cls.rows = {r["query_id"]: r for r in read_manifest(cls.corpus / "manifest.csv")}
        cls.audit = audit_fixture(cls.spec)

    def test_frozen_cohort_and_bands(self):
        pins = self.spec["replacements"]
        self.assertEqual(len(pins), 16)
        self.assertEqual(sum(r["semantic_tier"] == "low" for r in pins), 12)
        self.assertEqual(sum(r["query_id"].startswith("aggregate__") for r in pins), 4)
        for profile in self.audit["profiles"].values():
            self.assertTrue(retest.in_band(profile["observed_fraction"], profile["band"]))

    def test_every_query_changes_only_predicates_and_dataset_identity(self):
        for pin in self.spec["replacements"]:
            with self.subTest(query=pin["query_id"]):
                row = self.rows[pin["query_id"]]
                sql = (self.corpus / row["path"]).read_text()
                untouched = copy.deepcopy(row)
                new, rewritten = retest.transform(row, sql, pin, self.spec, self.audit)
                self.assertEqual(row, untouched)
                self.assertEqual(new["graph_dataset"], "epinions")
                self.assertNotEqual(new["query_id"], row["query_id"])
                self.assertNotEqual(new["content_sha256"], row["content_sha256"])
                self.assertNotEqual(new["sql_fingerprint"], row["sql_fingerprint"])
                for key in ("join_vector", "tree_shape", "expression_fingerprint", "aggregate_variant",
                            "target_fraction", "target_min_fraction", "target_max_fraction"):
                    self.assertEqual(new[key], row[key])
                self.assertEqual(count_base_relations(sql), count_base_relations(rewritten))
                restored = rewritten.split("\n", 1)[1].replace(new["selectivity_predicate"], row["selectivity_predicate"])
                for old, current in zip(json.loads(row["input_filter_profiles_json"]), json.loads(new["input_filter_profiles_json"])):
                    alias = old["relation"]
                    old_scan = "(SELECT src, dst FROM {0} WHERE {1}) {0}".format(alias, old["predicate"].replace(alias+".", ""))
                    new_scan = "(SELECT src, dst FROM {0} WHERE {1}) {0}".format(alias, current["predicate"].replace(alias+".", ""))
                    restored = restored.replace(new_scan, old_scan)
                self.assertEqual(restored, sql)

    def test_edited_source_and_metadata_fail_closed(self):
        pin = self.spec["replacements"][0]
        row = self.rows[pin["query_id"]]
        sql = (self.corpus / row["path"]).read_text()
        with self.assertRaisesRegex(ValueError, "SQL changed"):
            retest.transform(row, sql + "-- edit", pin, self.spec, self.audit)
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            retest.transform(dict(row, semantic_tier="high"), sql, pin, self.spec, self.audit)

    def test_prepare_is_idempotent_and_keeps_active_corpus_unchanged(self):
        before = {p: retest.digest(p) for p in self.corpus.rglob("*") if p.is_file()}
        with tempfile.TemporaryDirectory(prefix="graph-retest-") as tmp, \
                patch.object(retest, "calibrate", side_effect=lambda *args: copy.deepcopy(self.audit)):
            output = Path(tmp) / "epinions"
            retest.prepare(self.corpus, output, "unused", "unused")
            (output / "dataset_audit.json").unlink()  # Fresh git pull on CPU9.
            retest.prepare(self.corpus, output, "unused", "unused")
            rows = read_manifest(output / "manifest.csv")
            self.assertEqual(len(rows), 16)
            self.assertEqual(len(list(output.glob("graph/*.sql"))), 16)
            self.assertTrue(set(r["query_id"] for r in rows).isdisjoint(self.rows))
            path = output / rows[0]["path"]
            path.write_text(path.read_text() + "-- local edit")
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                retest.prepare(self.corpus, output, "unused", "unused")
        self.assertEqual(before, {p: retest.digest(p) for p in before})

    def test_output_cannot_be_inside_active_corpus(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            retest.prepare(self.corpus, self.corpus / "test", "unused", "unused")

    def test_incorrect_graph_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "wrong.duckdb"
            database.touch()
            with patch.object(retest, "identity", return_value={"n": 24186}), \
                    self.assertRaisesRegex(ValueError, "does not match"):
                retest.calibrate("unused", database, self.spec, json.loads(retest.DESIGN.read_text()))

    def test_bare_query_equivalence_on_small_duplicate_and_null_fixture(self):
        binary = Path(os.environ.get("DUCKDB_BIN", str(retest.SCRIPT.parent / "build/release/duckdb")))
        if not binary.is_file():
            self.skipTest("Local DuckDB binary not available")
        with tempfile.TemporaryDirectory(prefix="graph-retest-equivalence-") as tmp:
            database = Path(tmp) / "tiny.duckdb"
            edges = "(1,2),(1,2),(2,3),(3,1),(5,7),(7,8),(9,9),(20,NULL),(NULL,30),(120,2),(600,2),(900,120),(2200,1)"
            sql = "".join("CREATE TABLE R%d AS SELECT src::BIGINT src,dst::BIGINT dst "
                          "FROM (VALUES %s) edges(src,dst);" % (i, edges) for i in range(1, 6))
            subprocess.run([str(binary), str(database), "-bail", "-c", sql],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=15)
            for pin in self.spec["replacements"]:
                row = self.rows[pin["query_id"]]
                _, query = retest.transform(row, (self.corpus / row["path"]).read_text(), pin, self.spec, self.audit)
                outputs = []
                for mode in ("outer_yan", ""):
                    settings = "SET threads=4; SET max_execution_time=10000; SET disabled_optimizers='%s';" % mode
                    result = subprocess.run([str(binary), "-readonly", "-bail", "-no-init", "-csv", "-noheader",
                                             str(database), "-c", settings + query],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            universal_newlines=True, check=True, timeout=15)
                    outputs.append(sorted(result.stdout.splitlines()))
                self.assertEqual(outputs[0], outputs[1], row["query_id"])


if __name__ == "__main__":
    unittest.main()
