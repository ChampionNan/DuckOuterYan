import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from auto_test import reprocess_experiment_logs as RECOVER


LOG = """# class  : workload_category=v1 query_class=base
[ 1/2] query=measured
  result: correct=TRUE timing=measured aggregate=0 aggregate_pushdown=0 reorder=1 selected=OUTERYAN kernel=bitmap(b=2,h=0) threads=32 runtime_s=[DuckDB=2.123456789 OuterYan=1.000000000] speedup=2.123 optimization_s=[status=not-profiled DuckDB=NA OuterYan=NA overhead=NA ratio=NA samples=NA]
  context: family=tpch category=v1 nrel=3 pass=main note=OK rows=17 sql=tpch/measured.sql breakdown_s=[status=not-profiled CPU=NA R1=NA R2=NA R3=NA Other=NA wall=NA samples=NA]
  decision: plan=[mode=GATED reason=COST_OUTERYAN_BETTER raw_winner=OUTERYAN gate=PASS gate_applied=1 proven_empty=0 outer_yan_selected=1 formula=OUTER_YAN_COST_V9] risk=[retained=0.98 guard=0] cost=[OuterYan=50 + 1*20 = 70; DuckDB=100; delta=-30; raw_ratio=0.7] gate_cmp=[numeric:70 <= 120 (= 1.2*100); final=PASS; margin=50] SJ=[R1(build=2 probe=3 pairs=1 filters=1) R2(build=5 probe=10 pairs=2 filters=2) weighted=20]
[ 2/2] query=timeout
  result: correct=FALSE timing=not-run aggregate=0 aggregate_pushdown=0 reorder=1 selected=OUTERYAN kernel=not-run threads=32 runtime_s=[DuckDB=- OuterYan=-] speedup=- optimization_s=[status=not-correct DuckDB=NA OuterYan=NA overhead=NA ratio=NA samples=NA]
  context: family=tpcds category=v1 nrel=5 pass=main note=TIMEOUT rows=- sql=tpcds/timeout.sql breakdown_s=[status=not-correct CPU=NA R1=NA R2=NA R3=NA Other=NA wall=NA samples=NA]
  decision: gate_detail=[TIMEOUT (1800s, off): timeout]
"""


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.log = self.root / "experiment_onoff_benchmark_20260926_110332_t32_v1.txt"
        self.log.write_text(LOG)
        self.out = self.root / "reprocessed"

    def recover(self):
        _, output, info = RECOVER.recover(self.log, self.out)
        with output.open(newline="") as source:
            rows = list(csv.DictReader(source))
        return rows, info

    def sibling(self, rows):
        with self.log.with_suffix(".csv").open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_txt_recovers_costs_and_timeout_without_inventing_runtime(self):
        rows, info = self.recover()
        self.assertTrue(info["complete"])
        self.assertEqual(info["txt_only_rows"], 2)
        self.assertEqual(rows[0]["tm_off"], "2.123456789")
        self.assertEqual(rows[0]["candidate_total"], "70")
        self.assertEqual(rows[0]["cost_ratio_limit"], "1.2")
        self.assertEqual(rows[0]["round2_filters"], "2")
        self.assertEqual(rows[0]["baseline_join_input_rows"], "NA")
        self.assertEqual(rows[0]["optimizer_outeryan_phases_json"], "NA")
        self.assertEqual(rows[1]["correct"], "TIMEOUT")
        self.assertEqual(rows[1]["tm_off"], "-")
        self.assertEqual(rows[1]["candidate_total"], "NA")

    def test_sibling_precision_and_phase_maps_survive_recovery(self):
        original = {
            "query": "measured", "family": "tpch", "correct": "TRUE", "selected_plan": "OUTERYAN",
            "timing_threads": "32", "tm_off": "2.123456789123456", "tm_on": "1",
            "experiment_group": "20260926_113000", "optimizer_outeryan_phases_json": '{"other":0.1234567890123}',
        }
        self.sibling([original])
        before = self.log.with_suffix(".csv").read_bytes()
        rows, info = self.recover()
        self.assertEqual(info["txt_only_rows"], 1)
        self.assertEqual(rows[0]["tm_off"], original["tm_off"])
        self.assertEqual(rows[0]["optimizer_outeryan_phases_json"], original["optimizer_outeryan_phases_json"])
        self.assertEqual(rows[1]["experiment_group"], "20260926_113000")
        self.assertEqual(self.log.with_suffix(".csv").read_bytes(), before)

    def test_mismatched_sibling_is_rejected(self):
        self.sibling([{"query": "measured", "family": "tpch", "selected_plan": "DUCKDB"}])
        with self.assertRaisesRegex(ValueError, "TXT/CSV mismatch"):
            self.recover()

    def test_incomplete_log_is_reported_without_fabricating_rows(self):
        self.log.write_text(LOG.split("[ 2/2]")[0] + "[ 2/2] query=timeout\n  result: correct=FALSE\n")
        rows, info = self.recover()
        self.assertEqual(len(rows), 1)
        self.assertFalse(info["complete"])
        self.assertEqual(info["incomplete_log_blocks"], ["timeout"])

    def test_duplicate_blocks_are_rejected(self):
        self.log.write_text(LOG + LOG)
        with self.assertRaisesRegex(ValueError, "Duplicate query identities"):
            self.recover()

    def test_unversioned_log_recovers_revision_and_per_query_types(self):
        self.log = self.root / "experiment_onoff_benchmark_20260929_120000_t32.txt"
        self.log.write_text("# corpus : revision=unique-semantic-20260929, scope=benchmark\n" +
                            LOG.replace("category=v1", "category=join"))
        rows, info = self.recover()
        self.assertTrue(info["complete"])
        self.assertEqual(rows[0]["corpus_revision"], "unique-semantic-20260929")
        self.assertEqual(rows[0]["workload_category"], "join")
        self.assertEqual(rows[0]["query_class"], "join")
        self.assertEqual(rows[0]["corpus_version"], "")

    def test_source_output_collision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "separate --output-dir"):
            RECOVER.recover(self.log, self.root)

    def test_csv_only_requires_no_pandas_and_reports_missing_v3(self):
        self.assertEqual(RECOVER.main([str(self.log), "--output-dir", str(self.out), "--csv-only"]), 0)
        manifest = json.loads((self.out / "recovery_manifest.json").read_text())
        self.assertIn("v3_aggregation", manifest["groups"][0]["missing_categories"])
        self.assertEqual(manifest["groups"][0]["statistics"], "not-requested")


class OptionalArrowTest(unittest.TestCase):
    def test_csv_statistics_work_with_arrow_namespace_missing_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arrow = root / "pyarrow"
            arrow.mkdir()
            (arrow / "__init__.py").write_text("# Incomplete installation: no __version__.\n")
            log = root / "experiment_onoff_benchmark_20260926_110332_t32_v1.txt"
            log.write_text(LOG)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(root)
            out = root / "reprocessed"
            result = subprocess.run(
                [sys.executable, str(Path(RECOVER.__file__)), str(log), "--output-dir", str(out)],
                env=env, text=True, capture_output=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Ignoring incomplete optional pyarrow", result.stderr)
            report = json.loads(next(out.glob("*_statistics/statistics.json")).read_text())
            self.assertEqual(report["unique_queries"], 2)
            self.assertEqual(report["groups"][0]["counts"]["timeouts"], 1)
            self.assertAlmostEqual(report["groups"][0]["totals"]["off_s"], 2.123456789)
            self.assertEqual((arrow / "__init__.py").read_text(), "# Incomplete installation: no __version__.\n")


if __name__ == "__main__":
    unittest.main()
