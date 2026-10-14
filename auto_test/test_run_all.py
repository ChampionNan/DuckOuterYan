#!/usr/bin/env python3
"""Exercise run_all query selection without building databases or DuckDB."""

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


class RunAllSelectionTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="outeryan-run-all-")
        self.root = Path(self.scratch.name)
        self.scripts = self.root / "auto_test"
        self.scripts.mkdir()
        for name in ("configs.sh", "thread_sweep.sh", "run_all.sh"):
            shutil.copyfile(SCRIPT_DIR / name, self.scripts / name)

        self.log = self.root / "calls.jsonl"
        self.duckdb = self.root / "duckdb"
        self.duckdb.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        self.duckdb.chmod(0o755)

        (self.scripts / "build_db.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
        )
        (self.scripts / "build_db.sh").chmod(0o755)
        (self.scripts / "gen_outerjoin_benchmark.py").write_text(
            textwrap.dedent(
                """
                import json
                import os
                import sys
                with open(os.environ["RUN_ALL_TEST_LOG"], "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"kind": "generate", "args": sys.argv[1:]}) + "\\n")
                """
            ).lstrip(),
            encoding="utf-8",
        )
        for name, kind in (("verify_benchmark_reproduction.py", "verify"),
                           ("publish_plan_cohort.py", "publish")):
            (self.scripts / name).write_text(
                "import json, os, pathlib, sys\n"
                "args = sys.argv[1:]\n"
                "with open(os.environ['RUN_ALL_TEST_LOG'], 'a') as f:\n"
                f"    f.write(json.dumps(dict(kind={kind!r}, args=args)) + '\\n')\n"
                "if '--csv' in args and not pathlib.Path(args[args.index('--csv') + 1]).is_file():\n"
                "    sys.exit(4)\n"
                "if '--output-dir' in args:\n"
                "    pathlib.Path(args[args.index('--output-dir') + 1]).mkdir(parents=True, exist_ok=True)\n",
                encoding="utf-8")
        (self.scripts / "record_experiment.py").write_text(
            textwrap.dedent(
                """
                import json
                import os
                import pathlib
                import sys

                args = sys.argv[1:]
                with open(os.environ["RUN_ALL_TEST_LOG"], "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({
                        "kind": "experiment",
                        "args": args,
                        "corpus_present": "OY_CORPUS" in os.environ,
                        "tpch_sf": os.environ.get("TPCH_SF"),
                        "tpcds_sf": os.environ.get("TPCDS_SF"),
                        "tpch_db": os.environ.get("TPCH_DB"),
                        "tpcds_db": os.environ.get("TPCDS_DB"),
                        "timeout_seconds": os.environ.get("OY_TIMEOUT_SECS"),
                        "timing_runs": os.environ.get("OY_RUNS"),
                        "check_correctness": os.environ.get("OY_CHECK_CORRECTNESS"),
                    }) + "\\n")
                for option in ("-o", "--out"):
                    if option in args:
                        output = pathlib.Path(args[args.index(option) + 1])
                        output.parent.mkdir(parents=True, exist_ok=True)
                        output.write_text("ok\\n", encoding="utf-8")
                        if not os.environ.get("TEST_MISSING_CSV"):
                            output.with_suffix(".csv").write_text("query\\n", encoding="utf-8")
                        break
                sys.exit(int(os.environ.get("TEST_EXPERIMENT_STATUS", "0")))
                """
            ).lstrip(),
            encoding="utf-8",
        )
        (self.scripts / "experiment_onoff.sh").write_text(
            "#!/usr/bin/env bash\n"
            'exec "$PYTHON_BIN" "$(dirname "$0")/record_experiment.py" "$@"\n',
            encoding="utf-8",
        )
        (self.scripts / "experiment_onoff.sh").chmod(0o755)

    def tearDown(self):
        self.scratch.cleanup()

    def run_driver(self, *args, **overrides):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OY_", "PGPLAN_", "PG_REPLAY_", "DUCKDB_", "TPCH_", "TPCDS_"))
        }
        env.update(
            {
                "DUCKDB_BIN": str(self.duckdb),
                "PYTHON_BIN": sys.executable,
                "RUN_ALL_TEST_LOG": str(self.log),
                "SKIP_BUILD": "1",
                "SKIP_DATA": "1",
                "OY_THREADS": "2",
                "OY_THREAD_COUNTS": "2",
            }
        )
        env.update(overrides)
        return subprocess.run(
            ["bash", str(self.scripts / "run_all.sh"), "--no-figures", *args],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_default_uses_committed_queries_and_publishes_one_fresh_run(self):
        result = self.run_driver()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse([call for call in self.calls() if call["kind"] == "generate"])
        self.assertEqual([c["args"] for c in self.calls() if c["kind"] == "verify"], [["--validate-only"]])
        self.assertEqual(len([call for call in self.calls() if call["kind"] == "experiment"]), 1)
        experiment = next(call for call in self.calls() if call["kind"] == "experiment")
        self.assertEqual((experiment["tpch_sf"], experiment["tpcds_sf"]), ("50", "50"))
        self.assertEqual(Path(experiment["tpch_db"]), self.root / "tpch_50.duckdb")
        self.assertEqual(Path(experiment["tpcds_db"]), self.root / "tpcds_50.duckdb")
        self.assertEqual(experiment["timeout_seconds"], "600")
        self.assertEqual(experiment["timing_runs"], "5")
        self.assertEqual(experiment["check_correctness"], "0")
        published = next(c for c in self.calls() if c["kind"] == "publish")["args"]
        self.assertEqual(Path(published[published.index("--csv") + 1]), Path(experiment["args"][-1]).with_suffix(".csv"))
        self.assertNotIn("--latex", published)

    def test_measurement_options_are_forwarded(self):
        result = self.run_driver("--runs", "1", "--check-correctness")
        self.assertEqual(result.returncode, 0, result.stderr)
        experiment = next(call for call in self.calls() if call["kind"] == "experiment")
        runs_index = experiment["args"].index("--runs")
        self.assertEqual(experiment["args"][runs_index:runs_index + 3],
                         ["--runs", "1", "--check-correctness"])

    def test_explicit_timeout_environment_override_is_preserved(self):
        result = self.run_driver(OY_TIMEOUT_SECS="1200")
        self.assertEqual(result.returncode, 0, result.stderr)
        experiment = next(call for call in self.calls() if call["kind"] == "experiment")
        self.assertEqual(experiment["timeout_seconds"], "1200")

    def test_explicit_scale_overrides_are_preserved(self):
        result = self.run_driver(TPCH_SF="1", TPCDS_SF="10")
        self.assertEqual(result.returncode, 0, result.stderr)
        experiment = next(call for call in self.calls() if call["kind"] == "experiment")
        self.assertEqual((experiment["tpch_sf"], experiment["tpcds_sf"]), ("1", "10"))
        self.assertEqual(Path(experiment["tpch_db"]), self.root / "tpch_1.duckdb")
        self.assertEqual(Path(experiment["tpcds_db"]), self.root / "tpcds_10.duckdb")

    def test_sf100_paths_reach_experiment(self):
        result = self.run_driver("--all", TPCH_SF="100", TPCDS_SF="100")
        self.assertEqual(result.returncode, 0, result.stderr)
        experiment = next(call for call in self.calls() if call["kind"] == "experiment")
        self.assertEqual(Path(experiment["tpch_db"]), self.root / "tpch_100.duckdb")
        self.assertEqual(Path(experiment["tpcds_db"]), self.root / "tpcds_100.duckdb")

    def test_database_overrides_reach_experiment_unchanged(self):
        result = self.run_driver(TPCH_SF="100", TPCDS_SF="100", TPCH_DB="/preserved/tpch_db",
                                 TPCDS_DB="/preserved/tpcds_sf100.duckdb")
        self.assertEqual(result.returncode, 0, result.stderr)
        experiment = next(call for call in self.calls() if call["kind"] == "experiment")
        self.assertEqual(experiment["tpch_db"], "/preserved/tpch_db")
        self.assertEqual(experiment["tpcds_db"], "/preserved/tpcds_sf100.duckdb")

    def test_query_type_is_forwarded_without_duplicate_generation(self):
        result = self.run_driver("--query-type", "aggregate", "--timeout", "600")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse([call for call in self.calls() if call["kind"] in ("generate", "publish")])
        experiment = next(call for call in self.calls() if call["kind"] == "experiment")
        self.assertIn("--query-type", experiment["args"])
        self.assertIn("aggregate", experiment["args"])
        self.assertIn("600", experiment["args"])

    def test_retired_version_fails_before_build_or_generation(self):
        result = self.run_driver("--version", "v1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Version selection is retired", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_thread_sweep_preserves_custom_corpus(self):
        corpus = str(self.root / "custom")
        result = self.run_driver("--threads", "16,32", OY_CORPUS=corpus)
        self.assertEqual(result.returncode, 0, result.stderr)
        experiments = [call for call in self.calls() if call["kind"] == "experiment"]
        self.assertEqual(len(experiments), 2)
        for call, threads in zip(experiments, ("16", "32")):
            self.assertTrue(call["corpus_present"])
            self.assertNotIn("--all", call["args"])
            self.assertEqual(call["args"][-4:-2], ["--threads", threads])
            self.assertIn(f"_t{threads}.txt", call["args"][-1])

    def test_retired_pgplan_request_does_not_run_another_comparison(self):
        result = self.run_driver(RUN_PGPLAN="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PGPlan workflow has been removed", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_generation_is_explicit_and_verified(self):
        result = self.run_driver("--generate-queries")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c["kind"] for c in self.calls()], ["generate", "verify", "experiment", "publish"])
        self.assertNotIn("--validate-only", self.calls()[1]["args"])
        self.assertNotIn("--generate-queries", self.calls()[2]["args"])

    def test_prepare_only_does_not_test_or_publish(self):
        result = self.run_driver("--prepare-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c["kind"] for c in self.calls()], ["generate", "verify"])

    def test_report_only_does_not_generate_or_execute(self):
        source = self.root / "new.csv"
        source.touch()
        result = self.run_driver("--report-only", "--csv", str(source), "--date", "20261014")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c["kind"] for c in self.calls()], ["publish"])
        self.assertIn(str(source), self.calls()[0]["args"])

    def test_dry_run_and_help_have_no_stage_side_effects(self):
        for option in ("--dry-run", "--help"):
            result = self.run_driver(option)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.calls(), [])
            self.assertFalse((self.scripts / "results").exists())

    def test_no_history_substitution_and_experiment_failure_is_preserved(self):
        result = self.run_driver(TEST_EXPERIMENT_STATUS="7")
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(self.calls()[-1]["kind"], "publish")
        # Both stub runs may have the same second-resolution timestamp.
        experiment = next(c for c in self.calls() if c["kind"] == "experiment")
        Path(experiment["args"][-1]).unlink()
        Path(experiment["args"][-1]).with_suffix(".csv").unlink()
        result = self.run_driver(TEST_MISSING_CSV="1")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("no historical results substituted", result.stderr)

    def test_full_thread_sweep_keeps_reports_separate(self):
        result = self.run_driver("--threads", "16,32")
        self.assertEqual(result.returncode, 0, result.stderr)
        publications = [c["args"] for c in self.calls() if c["kind"] == "publish"]
        self.assertEqual([Path(a[a.index("--output-dir") + 1]).name for a in publications], ["t16", "t32"])

    def test_explicit_correctness_environment_is_preserved(self):
        result = self.run_driver(OY_CHECK_CORRECTNESS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        experiment = next(c for c in self.calls() if c["kind"] == "experiment")
        self.assertEqual(experiment["check_correctness"], "1")

    def test_report_only_local_history_dry_run(self):
        result = self.run_driver("--report-only", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
