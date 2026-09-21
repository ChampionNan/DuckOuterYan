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
        for name in ("configs.sh", "thread_sweep.sh", "experiment_onoff.sh", "phase_profile.sh"):
            shutil.copyfile(SCRIPT_DIR / name, self.scripts / name)
        corpus = self.root / "corpus" / "tpch"
        corpus.mkdir(parents=True)
        (corpus / "sample.sql").write_text("SELECT * FROM example;\n", encoding="utf-8")
        v1_corpus = self.scripts / "outerjoin_query" / "tpch"
        v1_corpus.mkdir(parents=True)
        (v1_corpus / "sample.sql").write_text(
            "SELECT * FROM example;\n", encoding="utf-8"
        )
        v2_corpus = self.scripts / "outerjoin_benchmark" / "v2" / "benchmark" / "tpch"
        v2_corpus.mkdir(parents=True)
        (v2_corpus / "sample.sql").write_text(
            "SELECT * FROM example;\n", encoding="utf-8"
        )
        for scope in ("selectivity_stress", "job_regressions"):
            scoped_corpus = self.scripts / "outerjoin_benchmark" / "v2" / scope / "tpch"
            scoped_corpus.mkdir(parents=True)
            (scoped_corpus / "sample.sql").write_text(
                "SELECT * FROM example;\n", encoding="utf-8"
            )
        self.database = self.root / "tpch.db"
        self.database.touch()
        self.calls = self.root / "calls.jsonl"
        self.duckdb = self.root / "duckdb"
        self.duckdb.write_text(f"#!{sys.executable}\n" + textwrap.dedent(r'''
            import json, os, re, sys
            from pathlib import Path
            sql = sys.stdin.read()
            match = re.search(r"PRAGMA threads=(\d+)", sql)
            if not match or int(match[1]) <= 1:
                sys.exit("Error: single-thread or implicit threads")
            threads = int(match[1])
            timing = ".timer on" in sql
            profiling = "CALL enable_profiling(" in sql
            off = "disabled_optimizers TO 'outer_yan'" in sql
            if profiling and (timing or off):
                sys.exit("Error: profile mixed with performance timing or OFF")
            with open(os.environ["HARNESS_CALLS"], "a") as log:
                log.write(json.dumps({"threads": threads, "timing": timing, "profiling": profiling,
                                      "off": off, "sql": sql}) + "\n")
            if "EXPLAIN" in sql:
                trace = os.environ.get("DUCKDB_OYTRACE")
                if trace:
                    selected = os.environ.get("SELECTED_PLAN", "OUTERYAN")
                    Path(trace).write_text(
                        f"[OY_DECISION] formula_id=TEST selection_mode=GATED selected_plan={selected} "
                        f"outer_reordered=1 cost_gate_applied=1 outer_yan_selected={int(selected == 'OUTERYAN')} "
                        "reason=COST_OUTERYAN_BETTER baseline_proven_empty=0 round1_pairs=1 round2_pairs=0\n"
                    )
                print("plan")
            elif profiling:
                if os.environ.get("FAIL_PROFILE"):
                    print("Error: profile timeout", file=sys.stderr)
                    sys.exit(124)
                paths = re.findall(r"save_location='([^']+)'", sql)
                for index, path in enumerate(paths):
                    if os.environ.get("BAD_PROFILE_JSON"):
                        Path(path).write_text("invalid JSON")
                        continue
                    factor = max(index, 1)
                    nodes = [
                        {"operator_name": name, "operator_type": kind, "operator_timing": value * factor, "children": []}
                        for name, kind, value in [("SJ_BUILD_ROUND_1", "SJ_BUILD", 1),
                                                  ("SJ_PROBE_ROUND_1", "SJ_PROBE", 2),
                                                  ("HASH_JOIN", "HASH_JOIN", 3), ("SEQ_SCAN", "TABLE_SCAN", 4)]
                    ]
                    if os.environ.get("BAD_PROFILE_ROUND"):
                        nodes[0]["operator_name"] = "SJ_BUILD_ROUND_2"
                    root = {"query_name": "SELECT * FROM example;", "latency": [99, 8, 4, 6][index % 4],
                            "cpu_time": 10 * factor, "children": nodes}
                    Path(path).write_text(json.dumps(root))
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

    def read_row(self):
        with (self.root / "result.csv").open(newline="") as handle:
            return next(csv.DictReader(handle))

    def assert_result(self, path, threads, expected_correct="TRUE", expected_speedup="2.000"):
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn(None, row)
        self.assertFalse(any(key.startswith("t1_") for key in row))
        self.assertIn("profile_status", row)
        self.assertEqual(row["timing_threads"], str(threads))
        self.assertEqual(row["correct"], expected_correct)
        self.assertEqual(row["tm_speedup"], expected_speedup)
        self.assertFalse(path.with_suffix(".attempts.csv").exists())
        report = path.with_suffix(".txt").read_text()
        self.assertNotIn("T1:", report)
        return report

    def test_default_profiles_only_on_separately_at_32_threads(self):
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.assert_result(self.root / "result.csv", 32)
        self.assertIn("# corpus : version=v1", report)
        self.assertFalse((self.root / "result_t16.csv").exists())
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual({call["threads"] for call in calls}, {32})
        timed = [call for call in calls if call["timing"]]
        self.assertEqual(len(timed), 2)
        self.assertTrue(all(call["sql"].count("SELECT * FROM example;") == 4 for call in timed))
        self.assertTrue(all("CALL disable_profiling();" in call["sql"] for call in calls))
        profiles = [call for call in calls if call["profiling"]]
        self.assertEqual(len(profiles), 1)
        self.assertFalse(profiles[0]["off"])
        self.assertEqual(profiles[0]["sql"].count("SELECT * FROM example;"), 4)
        self.assertFalse(any(call["profiling"] for call in timed))
        row = self.read_row()
        self.assertEqual(row["profile_status"], "OK")
        self.assertEqual(row["profile_threads"], "32")
        self.assertEqual(row["profile_timed_samples"], "3")
        # Sample 3 is the median latency (6), not the mean of independently selected phases.
        self.assertEqual(float(row["profile_wall_time_s"]), 6)
        self.assertEqual(float(row["profile_round1_operator_s"]), 9)
        self.assertEqual(float(row["profile_round2_operator_s"]), 0)
        self.assertEqual(float(row["profile_round3_operator_s"]), 9)
        self.assertEqual(float(row["profile_total_time_s"]), 30)
        self.assertEqual(float(row["profile_cpu_time_s"]), 30)
        self.assertEqual(float(row["profile_other_elapsed_s"]), 12)
        self.assertEqual(row["profile_directory"], "-")
        self.assertFalse((self.root / "result.profiles").exists())

    def test_explicit_v2_version_is_recorded_and_invalid_versions_fail_early(self):
        result = self.run_harness("--corpus-version", "v2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.assert_result(self.root / "result.csv", 32)
        self.assertIn("# corpus : version=v2", report)

        self.calls.unlink()
        invalid = self.run_harness("--corpus-version", "v3")
        self.assertEqual(invalid.returncode, 2, invalid.stdout + invalid.stderr)
        self.assertIn("--corpus-version must be v1 or v2", invalid.stderr)
        self.assertFalse(self.calls.exists())

    def test_v2_scopes_are_explicit_and_v1_rejects_them(self):
        result = self.run_harness(
            "--corpus-version", "v2", "--corpus-scope", "selectivity-stress"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.assert_result(self.root / "result.csv", 32)
        self.assertIn("scope=selectivity-stress", report)
        self.assertIn("/v2/selectivity_stress", report)

        self.calls.unlink()
        invalid = self.run_harness("--corpus-scope", "job-regressions")
        self.assertEqual(invalid.returncode, 2, invalid.stdout + invalid.stderr)
        self.assertIn("requires --corpus-version v2", invalid.stderr)
        self.assertFalse(self.calls.exists())

    def test_all_runs_v1_then_v2_into_separate_result_files(self):
        result = self.run_harness("--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        v1_report = self.assert_result(self.root / "result_v1.csv", 32)
        v2_report = self.assert_result(self.root / "result_v2.csv", 32)
        self.assertIn("# corpus : version=v1", v1_report)
        self.assertIn("# corpus : version=v2", v2_report)
        self.assertLess(
            result.stderr.index("Running corpus version: v1"),
            result.stderr.index("Running corpus version: v2"),
        )
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(len([call for call in calls if call["timing"]]), 4)

        conflict = self.run_harness("--all", "--corpus-version", "v2")
        self.assertEqual(conflict.returncode, 2, conflict.stdout + conflict.stderr)
        self.assertIn("--all cannot be combined with --corpus-version", conflict.stderr)

    def test_explicit_sweep_runs_16_then_32(self):
        result = self.run_harness("--threads", "16,32")
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
        self.assertEqual([call["threads"] for call in calls if call["profiling"]], [16, 32])

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
        self.assertFalse(any(call["profiling"] and call["threads"] == 16 for call in calls))

    def test_failed_timing_is_not_counted_as_measured(self):
        result = self.run_harness("--threads", "16", FAIL_TIMING_THREADS="16")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = self.assert_result(self.root / "result.csv", 16, expected_speedup="NA")
        self.assertIn("timed=0", report)

    def test_no_profile_flag_preserves_unprofiled_performance(self):
        result = self.run_harness("--no-profile")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_result(self.root / "result.csv", 32)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(any(call["profiling"] for call in calls))
        row = self.read_row()
        self.assertEqual(row["profile_status"], "disabled")
        self.assertEqual(row["profile_wall_time_s"], "NA")
        self.assertEqual(row["profile_total_time_s"], "NA")
        self.assertFalse((self.root / "result.profiles").exists())

    def test_profile_flag_overrides_environment(self):
        result = self.run_harness("--profile", OY_PROFILE="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_result(self.root / "result.csv", 32)
        row = self.read_row()
        self.assertEqual(row["profile_status"], "OK")

    def test_duckdb_selected_queries_skip_profile(self):
        result = self.run_harness(SELECTED_PLAN="DUCKDB")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.read_row()
        self.assertEqual(row["profile_status"], "not-selected")
        self.assertEqual(row["tm_speedup"], "2.000")
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertFalse(any(call["profiling"] for call in calls))

    def test_profile_failures_keep_timing_and_do_not_fabricate_phases(self):
        for failure in ("FAIL_PROFILE", "BAD_PROFILE_JSON", "BAD_PROFILE_ROUND"):
            with self.subTest(failure=failure):
                result = self.run_harness(**{failure: "1"})
                self.assertEqual(result.returncode, 0, result.stderr)
                report = self.assert_result(self.root / "result.csv", 32)
                row = self.read_row()
                self.assertEqual(row["profile_status"], "ERROR")
                self.assertEqual(row["profile_wall_time_s"], "NA")
                self.assertEqual(row["profile_total_time_s"], "NA")
                self.assertEqual(row["profile_round1_operator_s"], "NA")
                self.assertTrue(Path(row["profile_directory"]).is_dir())
                self.assertIn("PROFILE-ERROR", report)

    def test_invalid_profile_setting_does_not_execute_queries(self):
        result = self.run_harness(OY_PROFILE="sometimes")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
