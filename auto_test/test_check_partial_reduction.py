"""Bounded partial-reduction diagnostics without executing benchmark queries."""

import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check_partial_reduction as check


TRACE = """==== partial reduction ====
root=R1 bottom_up=4->3 top_down=4->0

==== selected plan ====
example
[OY_DECISION] selected_plan=OUTERYAN reason=COST_OUTERYAN_BETTER selection_mode=GATED cost_gate_applied=1 round1_pairs=4 round1_filters=4 round2_pairs=4 round2_filters=4 executed_round1_pairs=3 executed_round1_filters=2 executed_round2_pairs=0 executed_round2_filters=0
"""


class PartialReductionDiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="outeryan-partial-diagnostic-test-")
        self.root = Path(self.scratch.name)
        self.corpus = self.root / "corpus"
        self.corpus.mkdir()
        self.csv = self.root / "original.csv"
        self.rows = []
        self.metadata = []

    def tearDown(self):
        self.scratch.cleanup()

    def add_query(self, family="tpch", off="2", on="4", **changes):
        name = f"q{len(self.rows)}"
        relative = family + "/" + name + ".sql"
        path = self.corpus / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text("-- fixture\nSELECT * FROM example;\n", encoding="utf-8")
        row = dict(query=name, family=family, sql_path=relative, tm_off=off, tm_on=on,
                   correct="TRUE", correctness_check="enabled", timing_status="measured", note="OK",
                   duckdb_status="measured", outeryan_status="measured", sql_content_sha256=check.digest(path))
        row.update(changes)
        self.rows.append(row)
        self.metadata.append(dict(path=relative, content_sha256=check.digest(path)))
        return row

    def save(self):
        for path, rows in ((self.csv, self.rows), (self.corpus / "manifest.csv", self.metadata)):
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

    def cohort(self, **kwargs):
        self.save()
        return check.load_cohort(self.csv, corpus=self.corpus, **kwargs)

    def test_excludes_invalid_policy_timeouts_and_threshold_boundary(self):
        kept = self.add_query(off="0.01", on="0.02", correct="True")
        self.add_query(off="0.8", on="1")
        self.add_query(timing_status="fallback-skip")
        self.add_query(note="TIMEOUT")
        self.add_query(outeryan_status="timeout")
        self.add_query(correct="FALSE")
        self.add_query(correct="NOT-CHECKED", correctness_check="enabled")
        self.add_query(off="nan")
        self.add_query(on="inf")
        self.add_query(on="0")
        self.add_query(off="-1")
        self.add_query(timing_status="not-run")
        self.assertEqual([row["query"] for row in self.cohort()], [kept["query"]])

    def test_family_alias_limit_and_added_wall_priority(self):
        self.add_query(family="job", off="2", on="10")
        self.add_query(family="tpch", off="2", on="4")
        largest = self.add_query(family="tpch", off="4", on="10")
        largest["family"] = "TPC-H"
        rows = self.cohort(families=["tpch"], limit=1)
        self.assertEqual(rows[0]["query"], largest["query"])
        self.assertEqual(rows[0]["source_added_wall_s"], 6)

    def test_unchecked_requires_explicit_opt_out(self):
        self.add_query(correct="NOT-CHECKED", correctness_check="disabled")
        self.assertEqual(len(self.cohort()), 1)

    def test_rejects_changed_sql_and_stale_measurement(self):
        row = self.add_query()
        self.save()
        (self.corpus / row["sql_path"]).write_text("SELECT 2;", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Measured SQL differs"):
            check.load_cohort(self.csv, corpus=self.corpus)

    def test_rejects_duplicate_measured_identity(self):
        self.add_query()
        self.rows.append(dict(self.rows[0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.cohort()

    def test_rejects_path_escape(self):
        self.add_query(sql_path="../outside.sql")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.cohort()

    def test_requires_one_bare_select(self):
        path = self.root / "query.sql"
        path.write_text("SELECT ';' AS semicolon -- comment\n", encoding="utf-8")
        self.assertTrue(check.query_text(path).endswith("\n;"))
        for sql in ("SELECT 1; SELECT 2;", "COPY (SELECT 1) TO 'x';", "CREATE TABLE x AS SELECT 1;"):
            path.write_text(sql, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bare SELECT"):
                check.query_text(path)

    def test_trace_separates_cost_reference_from_actual_schedule(self):
        result = check.parse_trace(TRACE)
        self.assertEqual(result["reference_cost_counts"]["round2_pairs"], 4)
        self.assertEqual(result["scheduled_counts"]["round2_pairs"], 0)
        self.assertEqual(result["scheduled_counts"]["round1_filters"], 2)
        self.assertEqual(result["partial_reduction_stages"], ["root=R1 bottom_up=4->3 top_down=4->0"])
        self.assertEqual(check.parse_trace(TRACE + TRACE)["decision_count"], 2)
        self.assertFalse(check.parse_trace("")["scheduled_counts_available"])

    @patch.object(check.subprocess, "run")
    def test_readonly_normal_gate_and_environment_isolation(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "plan", "")
        env = dict(os.environ, DUCKDB_OY_FORCE_CANDIDATE="1", DUCKDB_OY_SIMPLIFY_SCAN_FILTERS="1",
                   DUCKDB_OY_PROFILE_TRACE="unwanted", FORCE="1")
        result = check.run_process("duckdb", "db", "EXPLAIN SELECT 1;", 35,
                                   trace=self.root / "private.trace", environ=env)
        args, kwargs = run.call_args
        self.assertIn("-readonly", args[0])
        self.assertIn("-no-init", args[0])
        self.assertEqual(kwargs["timeout"], 35)
        self.assertEqual(kwargs["env"]["DUCKDB_OYTRACE"], str(self.root / "private.trace"))
        for key in check.UNSAFE_ENV:
            if key != "DUCKDB_OYTRACE":
                self.assertNotIn(key, kwargs["env"])
        self.assertEqual(env["DUCKDB_OY_FORCE_CANDIDATE"], "1")
        self.assertEqual(result["status"], "ok")

    @patch.object(check.subprocess, "run")
    def test_watchdog_is_reported_without_a_timing_sample(self, run):
        run.side_effect = subprocess.TimeoutExpired([], 35, output=b"partial")
        result = check.run_process("duckdb", "db", "SELECT 1;", 35)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["stdout"], "partial")

    @patch.object(check, "run_process")
    def test_default_explain_only_and_optional_bare_postwarmup_timing(self, run):
        trace = self.root / "q.trace"
        trace.write_text(TRACE, encoding="utf-8")
        run.return_value = {"status": "ok", "stdout": "plan", "stderr": ""}
        result = check.diagnose_mode("duckdb", "db", "SELECT * FROM example;", True, 4, 30, trace)
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("timing", result)
        self.assertIn("SET VARIABLE outer_yan_partial_reduction = true", run.call_args.args[2])
        self.assertIn("EXPLAIN SELECT", run.call_args.args[2])
        run.reset_mock()
        run.side_effect = [{"status": "ok", "stdout": "plan", "stderr": ""},
                           {"status": "ok", "stdout": "OY_WARMUP_DONE\nRun Time (s): real 0.125000000 user 0 sys 0\n", "stderr": ""}]
        result = check.diagnose_mode("duckdb", "db", "SELECT * FROM example;", False, 4, 30, trace, execute=True)
        timing_call = run.call_args_list[1]
        timing_sql = timing_call.args[2]
        self.assertEqual(timing_sql.count("SELECT * FROM example;"), 2)
        self.assertEqual(timing_sql.split(".timer on\n")[1].count("SELECT * FROM example;"), 1)
        self.assertIn(".mode trash", timing_sql)
        self.assertIn("SET max_execution_time=30000", timing_sql)
        self.assertNotIn("EXPLAIN", timing_sql)
        self.assertNotIn("CTAS", timing_sql)
        self.assertEqual(timing_call.args[3], 65)
        self.assertEqual(len(timing_call.args), 4)  # No trace on measured process.
        self.assertEqual(result["timing"]["sample_s"], .125)
        self.assertEqual(result["timing"]["correctness"], "NOT-CHECKED")

    @patch.object(check, "run_process")
    def test_old_binary_without_counter_support_cannot_fake_success(self, run):
        trace = self.root / "old.trace"
        trace.write_text("[OY_DECISION] selected_plan=OUTERYAN round1_pairs=4\n", encoding="utf-8")
        run.return_value = {"status": "ok", "stdout": "plan", "stderr": ""}
        result = check.diagnose_mode("duckdb", "db", "SELECT 1;", True, 4, 30, trace, execute=True)
        self.assertEqual(result["explain"]["status"], "error")
        self.assertEqual(result["timing"]["status"], "not-run")
        self.assertEqual(run.call_count, 1)

    @patch.object(check, "run_process")
    def test_rejects_forced_selection_or_disabled_cost_gate(self, run):
        trace = self.root / "forced.trace"
        for text in (TRACE.replace("selection_mode=GATED", "selection_mode=FORCE_OUTERYAN"),
                     TRACE.replace("cost_gate_applied=1", "cost_gate_applied=0")):
            trace.write_text(text, encoding="utf-8")
            run.return_value = {"status": "ok", "stdout": "plan", "stderr": ""}
            result = check.diagnose_mode("duckdb", "db", "SELECT 1;", True, 4, 30, trace)
            self.assertEqual(result["explain"]["status"], "error")
            self.assertIn("normally gated", result["explain"]["error"])

    def test_refuses_to_overwrite_original_or_existing_report(self):
        report = self.root / "existing.json"
        report.write_text("preserve", encoding="utf-8")
        with self.assertRaises(SystemExit):
            check.main(["--csv", str(self.csv), "--out", str(report)])
        self.assertEqual(report.read_text(), "preserve")

    def test_end_to_end_timeout_is_independent_and_sources_are_unchanged(self):
        self.add_query()
        self.save()
        source_before = self.csv.read_bytes()
        database = self.root / "tpch_1.duckdb"
        database.write_bytes(b"read-only fixture")
        binary = self.root / "duckdb"
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o755)
        output = self.root / "diagnostic.json"
        calls = []

        def run(binary, database, sql, timeout, trace=None):
            calls.append(sql)
            if trace is not None:
                trace.write_text(TRACE, encoding="utf-8")
                return {"status": "ok", "stdout": "plan", "stderr": ""}
            if "partial_reduction = false" in sql:
                return {"status": "timeout", "stdout": "", "error": "watchdog expired"}
            return {"status": "ok", "stdout": "Run Time (s): real 0.25 user 0 sys 0\n", "stderr": ""}

        with patch.object(check, "CORPUS", self.corpus), patch.object(check, "run_process", side_effect=run), \
                patch.dict(os.environ, {"TPCH_DB": str(database), "TPCH_SF": "1"}):
            code = check.main(["--csv", str(self.csv), "--out", str(output), "--duckdb", str(binary),
                               "--execute", "--label", "verified-separately-SF1"])
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 4)
        self.assertEqual(report["failed_modes"], 1)
        self.assertTrue(report["inputs_unchanged"])
        self.assertEqual(report["rows"][0]["modes"]["enabled"]["timing"]["sample_s"], .25)
        self.assertIsNone(report["rows"][0]["partial_reduction_speedup"])
        self.assertEqual(report["databases"]["tpch"]["configured_scale_parameter"], "1")
        self.assertEqual(report["databases"]["tpch"]["actual_scale"], "unverified by this runner")
        self.assertEqual(self.csv.read_bytes(), source_before)
        self.assertEqual(database.read_bytes(), b"read-only fixture")

    def test_database_metadata_does_not_accept_directory(self):
        with self.assertRaisesRegex(ValueError, "Database file does not exist"):
            check.database_metadata(self.root, "tpch")


if __name__ == "__main__":
    unittest.main()
