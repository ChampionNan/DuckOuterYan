#!/usr/bin/env python3
"""Exercise the real shell harness with a tiny, deterministic DuckDB stand-in."""

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent


class MultiThreadExperimentTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="outeryan-threads-")
        self.root = Path(self.scratch.name)
        self.scripts = self.root / "auto_test"
        self.scripts.mkdir()
        for name in ("configs.sh", "thread_sweep.sh", "experiment_onoff.sh"):
            shutil.copyfile(SCRIPT_DIR / name, self.scripts / name)
        corpus = self.root / "corpus" / "tpch"
        corpus.mkdir(parents=True)
        (corpus / "sample.sql").write_text("SELECT * FROM example;\n", encoding="utf-8")
        self.database = self.root / "tpch.db"
        self.database.touch()
        self.calls = self.root / "calls.jsonl"
        self.duckdb = self.root / "duckdb"
        self.duckdb.write_text(f"#!{sys.executable}\n" + textwrap.dedent(r'''
            import json, os, re, sys
            from pathlib import Path
            sql = sys.stdin.read()
            match = re.search(r"PRAGMA threads=(\d+)", sql)
            if not match or int(match[1]) <= 1 or "enable_profiling" in sql:
                sys.exit("Error: single-thread, implicit threads, or profiling execution")
            threads = int(match[1])
            timing = ".timer on" in sql
            off = "disabled_optimizers TO 'outer_yan'" in sql
            with open(os.environ["HARNESS_CALLS"], "a") as log:
                log.write(json.dumps({"threads": threads, "timing": timing, "off": off, "sql": sql}) + "\n")
            if "EXPLAIN" in sql:
                trace = os.environ.get("DUCKDB_OYTRACE")
                if trace:
                    Path(trace).write_text(
                        "[OY_DECISION] formula_id=TEST selection_mode=GATED selected_plan=OUTERYAN "
                        "outer_reordered=1 cost_gate_applied=1 outer_yan_selected=1 reason=COST_OUTERYAN_BETTER\n"
                    )
                print("plan")
            elif timing:
                if os.environ.get("FAIL_TIMING_THREADS") == str(threads):
                    sys.exit("Error: timing failed")
                count = len(re.findall(r"(?m)^SELECT ", sql))
                for index in range(count):
                    seconds = 99 if index == 0 else (160 if off else 80) / threads
                    print(f"Run Time (s): real {seconds:.9f} user 0 sys 0")
            elif os.environ.get("DUCKDB_SJ_KERNEL_TRACE"):
                print("[SJ_KERNEL] BITMAP", file=sys.stderr)
            else:
                mismatch = os.environ.get("FAIL_CORRECTNESS_THREADS") == str(threads)
                print("43" if mismatch and not off else "42")
        ''').lstrip(), encoding="utf-8")
        self.duckdb.chmod(0o755)

    def tearDown(self):
        self.scratch.cleanup()

    def run_harness(self, *args, **overrides):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("OY_", "PGPLAN_", "PG_REPLAY_", "DUCKDB_"))}
        env.update({
            "DUCKDB_BIN": str(self.duckdb), "TPCH_DB": str(self.database),
            "OY_CORPUS": str(self.root / "corpus"), "OY_TMPDIR": str(self.root / "tmp"),
            "OY_TIMEOUT_SECS": "0", "HARNESS_CALLS": str(self.calls), "LC_ALL": "C",
        })
        env.update(overrides)
        result = subprocess.run(
            ["bash", str(self.scripts / "experiment_onoff.sh"), "--only", "tpch",
             "--capture-plans", "--out", str(self.root / "result.txt"), *args],
            env=env, text=True, capture_output=True, timeout=45,
        )
        return result

    def assert_result(self, path, threads, expected_correct="TRUE", expected_speedup="2.000"):
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn(None, row)
        self.assertFalse(any(key.startswith(("t1_", "profile_")) for key in row))
        self.assertEqual(row["timing_threads"], str(threads))
        self.assertEqual(row["correct"], expected_correct)
        self.assertEqual(row["tm_speedup"], expected_speedup)
        self.assertEqual(path.read_bytes(), path.with_suffix(".attempts.csv").read_bytes())
        report = path.with_suffix(".txt").read_text()
        self.assertNotIn("T1:", report)
        self.assertNotIn("profile=[", report)
        self.assertNotIn("CPU-Time", report)
        return report

    def test_default_runs_16_then_32_without_single_thread_or_profiling(self):
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for threads in (16, 32):
            self.assert_result(self.root / f"result_t{threads}.csv", threads)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual({call["threads"] for call in calls}, {16, 32})
        self.assertEqual([call["threads"] for call in calls], sorted(call["threads"] for call in calls))
        timed = [call for call in calls if call["timing"]]
        self.assertEqual(len(timed), 4)
        self.assertTrue(all(call["sql"].count("SELECT * FROM example;") == 4 for call in timed))
        self.assertTrue(all("CALL disable_profiling();" in call["sql"] for call in calls))

    def test_cli_single_override_takes_precedence_and_preserves_explicit_out(self):
        result = self.run_harness("--threads", "8", OY_THREAD_COUNTS="16 32")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_result(self.root / "result.csv", 8)
        self.assertFalse((self.root / "result_t16.csv").exists())

    def test_scalar_environment_override_runs_once(self):
        result = self.run_harness(OY_THREADS="8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_result(self.root / "result.csv", 8)

    def test_invalid_thread_lists_do_not_execute_queries(self):
        for specification in ("", "1", "16 1", "16,16", "0", "-2", "16 nope"):
            with self.subTest(specification=specification):
                result = self.run_harness("--threads", specification)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(self.calls.exists())

    def test_failed_correctness_is_not_timed_but_other_thread_config_runs(self):
        result = self.run_harness("--threads", "16,32", FAIL_CORRECTNESS_THREADS="16")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_result(self.root / "result_t16.csv", 16, "FALSE", "-")
        self.assert_result(self.root / "result_t32.csv", 32)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(any(call["timing"] and call["threads"] == 16 for call in calls))

    def test_failed_timing_is_not_counted_as_measured(self):
        result = self.run_harness("--threads", "16", FAIL_TIMING_THREADS="16")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.assert_result(self.root / "result.csv", 16, expected_speedup="NA")
        self.assertIn("timed=0", report)


if __name__ == "__main__":
    unittest.main()
