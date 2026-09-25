#!/usr/bin/env python3
"""Focused wiring tests for run_all.sh's two-way and opt-in PGPlan stages."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


SOURCE_RUN_ALL = Path(__file__).resolve().parents[1] / "run_all.sh"
SOURCE_CONFIGS = Path(__file__).resolve().parents[1] / "configs.sh"
SOURCE_THREAD_SWEEP = Path(__file__).resolve().parents[1] / "thread_sweep.sh"


class RunAllPGPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name) / "repo"
        self.auto_test = self.repo / "auto_test"
        self.pgplan = self.auto_test / "pgplan"
        self.pgplan.mkdir(parents=True)
        (self.auto_test / "outerjoin_benchmark" / "benchmark").mkdir(parents=True)
        (self.auto_test / "outerjoin_benchmark" / "industry_inspired" / "tpch").mkdir(
            parents=True
        )

        shutil.copy2(SOURCE_RUN_ALL, self.auto_test / "run_all.sh")
        shutil.copy2(SOURCE_THREAD_SWEEP, self.auto_test / "thread_sweep.sh")
        self.duckdb = self.repo / "fake-duckdb"
        self.duckdb.touch()
        self.duckdb.chmod(0o755)
        self.execution_db = self.repo / "tpch_db"
        self.execution_db.touch()
        self.query = (
            self.auto_test
            / "outerjoin_benchmark"
            / "industry_inspired"
            / "tpch"
            / "oy_th_real_supplier_right.sql"
        )
        self.query.write_text("SELECT 1;\n", encoding="utf-8")
        self.log = self.repo / "calls.log"

        self._write(
            self.auto_test / "configs.sh",
            f"""
            OY_REPO_ROOT="{self.repo}"
            export DUCKDB_BIN="${{DUCKDB_BIN:-{self.duckdb}}}"
            export TPCH_DB="${{TPCH_DB:-{self.execution_db}}}"
            export OY_CORPUS="${{OY_CORPUS:-{self.repo / 'configured-default-corpus'}}}"
            export OY_RUNS="${{OY_RUNS:-3}}"
            export OY_THREADS="${{OY_THREADS:-7}}"
            export OY_TIMEOUT_SECS="${{OY_TIMEOUT_SECS:-90}}"
            export OY_BATCH_GRACE_SECS="${{OY_BATCH_GRACE_SECS:-4}}"
            export OY_TMPDIR="${{OY_TMPDIR:-{self.repo / 'tmp'}}}"
            export RUN_PGPLAN="${{RUN_PGPLAN:-0}}"
            export PGPLAN_QUERY="${{PGPLAN_QUERY:-{self.query}}}"
            export PGPLAN_EXECUTION_DB="${{PGPLAN_EXECUTION_DB:-$TPCH_DB}}"
            export PGPLAN_RUNS="${{PGPLAN_RUNS:-$OY_RUNS}}"
            export PGPLAN_THREADS="${{PGPLAN_THREADS:-$OY_THREADS}}"
            export PGPLAN_PLAN_CACHE="${{PGPLAN_PLAN_CACHE:-{self.repo / 'auto_test/pgplan/plans'}}}"
            export PGPLAN_COMPARISON_MODE="${{PGPLAN_COMPARISON_MODE:-both}}"
            export PGPLAN_CORRECTNESS_MODE="${{PGPLAN_CORRECTNESS_MODE:-target}}"
            export PGPLAN_CORRECTNESS_FROM="${{PGPLAN_CORRECTNESS_FROM:-}}"
            export PGPLAN_REUSE_FROM="${{PGPLAN_REUSE_FROM:-}}"
            export PGPLAN_CAPTURE_TIMEOUT_SECS="${{PGPLAN_CAPTURE_TIMEOUT_SECS:-300}}"
            export PGPLAN_TIMEOUT_SECS="${{PGPLAN_TIMEOUT_SECS:-$OY_TIMEOUT_SECS}}"
            export PGPLAN_TIMEOUT_GRACE="${{PGPLAN_TIMEOUT_GRACE:-$OY_BATCH_GRACE_SECS}}"
            export PGPLAN_TMPDIR="${{PGPLAN_TMPDIR:-$OY_TMPDIR}}"
            export PGPLAN_VERSION_NUM=160002
            export PG_DSN='host=127.0.0.1 port=55432 dbname=duckyan_tpch user=postgres'
            """,
        )
        self._write_executable(
            self.pgplan / "corpus_experiment.sh",
            """
            out=''
            args="$*"
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    --out) out="$2"; shift 2 ;;
                    *) shift ;;
                esac
            done
            [ -n "$out" ]
            mkdir -p "$out/artifacts"
            printf 'family\tquery\tstatus\n' > "$out/status.tsv"
            : > "$out/comparison.tsv"
            : > "$out/comparison.csv"
            : > "$out/comparison.log"
            : > "$out/summary.tsv"
            : > "$out/failures.tsv"
            printf 'corpus\t%s\t%s\n' "${SKIP_PG_DATA:-unset}" "$args" >> "$HARNESS_LOG"
            exit "${HARNESS_EXIT_CODE:-0}"
            """,
        )
        self._write_executable(
            self.auto_test / "experiment_onoff.sh",
            """
            printf 'onoff\t%s\t%s\n' "$OY_CORPUS" "$*" >> "$HARNESS_LOG"
            """,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @staticmethod
    def _write(path: Path, body: str) -> None:
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")

    def _write_executable(self, path: Path, body: str) -> None:
        self._write(path, "#!/usr/bin/env bash\nset -euo pipefail\n" + body)
        path.chmod(0o755)

    def _run(self, *args: str, **overrides: str) -> subprocess.CompletedProcess[str]:
        inject_default_skips = overrides.pop("_inject_default_skips", "1") == "1"
        env = os.environ.copy()
        for name in (
            "DUCKDB_BIN",
            "OY_CONFIG_LOADED",
            "OY_CORPUS",
            "OY_THREADS",
            "OY_THREAD_COUNTS",
            "RUN_PGPLAN",
            "RUN_PG_REPLAY",
            "PGPLAN_QUERY",
            "PGPLAN_EXECUTION_DB",
            "PGPLAN_RUNS",
            "PGPLAN_THREADS",
            "PGPLAN_PLAN_CACHE",
            "PGPLAN_COMPARISON_MODE",
            "PGPLAN_CORRECTNESS_MODE",
            "PGPLAN_CORRECTNESS_FROM",
            "PGPLAN_REUSE_FROM",
            "PGPLAN_CAPTURE_TIMEOUT_SECS",
            "PGPLAN_TIMEOUT_SECS",
            "PGPLAN_TIMEOUT_GRACE",
            "PGPLAN_TMPDIR",
            "PGPLAN_OUT",
            "PGPLAN_PLAN_OUT",
            "PGPLAN_SETUP",
            "PGPLAN_INSTALL_DIR",
            "PGPLAN_PASSWORD_FILE",
            "PGPLAN_PASSWORD",
            "PGPLAN_CONTAINER_PASSWORD",
            "PG_REPLAY_PASSWORD",
            "PG_REPLAY_CONTAINER_PASSWORD",
            "PGPASSWORD",
            "PG_REPLAY_QUERY",
            "PG_REPLAY_EXECUTION_DB",
            "PG_REPLAY_RUNS",
            "PG_REPLAY_THREADS",
            "PG_REPLAY_CAPTURE_TIMEOUT_SECS",
            "PG_REPLAY_TIMEOUT_SECS",
            "PG_REPLAY_TIMEOUT_GRACE",
            "PG_REPLAY_TMPDIR",
            "PG_REPLAY_OUT",
            "PG_REPLAY_PLAN_OUT",
            "HARNESS_EXIT_CODE",
            "SKIP_BUILD",
            "SKIP_DATA",
            "SKIP_QUERY_GEN",
        ):
            env.pop(name, None)
        env["HARNESS_LOG"] = str(self.log)
        if inject_default_skips:
            env.update(
                {
                    "SKIP_BUILD": "1",
                    "SKIP_DATA": "1",
                    "SKIP_QUERY_GEN": "1",
                }
            )
        env.update(overrides)
        return subprocess.run(
            ["bash", str(self.auto_test / "run_all.sh"), *args],
            cwd=self.repo,
            env=env,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def test_default_runs_only_original_outeryan_experiment(self) -> None:
        result = self._run("--limit", "1")
        self.assertEqual(result.returncode, 0, result.stdout)

        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("onoff\t"), calls)
        self.assertIn(str(self.auto_test / "outerjoin_benchmark" / "benchmark"), calls[0])
        self.assertIn("--only all", calls[0])
        self.assertIn("--limit 1", calls[0])
        self.assertIn(
            "PGPlan disabled; running default Original/OuterYan workflow",
            result.stdout,
        )
        self.assertNotIn("persistent PGPlan cache", result.stdout)
        self.assertNotIn("Comparison status TSV:", result.stdout)

    def test_thread_sweep_runs_two_configurations_with_separate_outputs(self) -> None:
        result = self._run("--limit", "1", OY_THREAD_COUNTS="16 32")
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 2)
        for call, threads in zip(calls, (16, 32)):
            self.assertIn(f"--threads {threads}", call)
            self.assertIn(f"_t{threads}.txt", call)
            self.assertIn(f"_t{threads}.csv", result.stdout)

    def test_pgplan_thread_sweep_uses_separate_output_directories(self) -> None:
        output_base = str(self.repo / "pgplan-results")
        result = self._run("--out", output_base, RUN_PGPLAN="1", OY_THREAD_COUNTS="16 32")
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 2)
        for call, threads in zip(calls, (16, 32)):
            self.assertTrue(call.startswith("corpus\t"), call)
            self.assertTrue(call.endswith(f"--threads {threads} --out {output_base}_t{threads}"), call)
            self.assertTrue(Path(f"{output_base}_t{threads}/comparison.csv").is_file())

    def test_cli_thread_count_overrides_sweep(self) -> None:
        result = self._run("--threads", "8", OY_THREAD_COUNTS="16 32")
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1)
        self.assertIn("_t8.txt", calls[0])

    def test_explicit_opt_in_runs_corpus_wide_three_way_experiment(self) -> None:
        cli_duckdb = self.repo / "cli-duckdb"
        cli_duckdb.touch()
        cli_duckdb.chmod(0o755)
        result_dir = self.repo / "threeway-results"
        result = self._run(
            "--bin",
            str(cli_duckdb),
            "--runs",
            "5",
            "--timeout",
            "12",
            "--capture-timeout",
            "23",
            "--only",
            "tpch",
            RUN_PGPLAN="1",
            PGPLAN_OUT=str(result_dir),
        )
        self.assertEqual(result.returncode, 0, result.stdout)

        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1)
        fields = calls[0].split("\t", 2)
        self.assertEqual(fields[0], "corpus")
        # SKIP_DATA must not silently disable loading PG's independent tiny data.
        self.assertEqual(fields[1], "unset")
        corpus_args = fields[2]
        self.assertIn(
            f"--corpus {self.auto_test / 'outerjoin_benchmark' / 'benchmark'}",
            corpus_args,
        )
        self.assertIn(f"--duckdb-bin {self.duckdb}", corpus_args)
        self.assertIn("--rows 1000", corpus_args)
        self.assertIn("--threads 7", corpus_args)
        self.assertIn(f"--bin {cli_duckdb}", corpus_args)
        self.assertIn("--runs 5", corpus_args)
        self.assertIn("--timeout 12", corpus_args)
        self.assertIn("--capture-timeout 23", corpus_args)
        self.assertIn("--only tpch", corpus_args)
        self.assertIn(
            "Checking the persistent PGPlan cache and preparing exact target-data comparisons",
            result.stdout,
        )
        self.assertIn(f"Comparison status TSV: {result_dir / 'status.tsv'}", result.stdout)
        self.assertIn(
            f"Comparison TSV: {result_dir / 'comparison.tsv'}", result.stdout
        )
        self.assertIn(
            f"Comparison CSV: {result_dir / 'comparison.csv'}", result.stdout
        )
        self.assertIn(
            f"Comparison detailed log: {result_dir / 'comparison.log'}", result.stdout
        )
        self.assertIn(f"Comparison summary TSV: {result_dir / 'summary.tsv'}", result.stdout)
        self.assertIn(
            f"Comparison failures TSV: {result_dir / 'failures.tsv'}", result.stdout
        )

    def test_run_all_reaches_cache_aware_corpus_with_unusable_pg_install(self) -> None:
        # Cache hit/miss detection happens inside the corpus runner, after
        # run_all sources configs.sh. Loading configuration must therefore be
        # filesystem-neutral when PostgreSQL is never needed.
        shutil.copy2(SOURCE_CONFIGS, self.auto_test / "configs.sh")
        blocker = self.repo / "unwritable-pg-parent"
        blocker.write_text("not a directory", encoding="utf-8")
        result = self._run(
            "--limit",
            "1",
            DUCKDB_BIN=str(self.duckdb),
            RUN_PGPLAN="1",
            PGPLAN_SETUP="source",
            PGPLAN_INSTALL_DIR=str(blocker / "postgresql"),
            PGPLAN_PASSWORD="",
            PGPLAN_CONTAINER_PASSWORD="",
            PG_REPLAY_PASSWORD="",
            PG_REPLAY_CONTAINER_PASSWORD="",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(blocker.is_file())
        self.assertIn("corpus\t", self.log.read_text(encoding="utf-8"))

    def test_corpus_failure_prints_handoff_then_preserves_exit_status(self) -> None:
        result_dir = self.repo / "failed-threeway-results"
        result = self._run(
            RUN_PGPLAN="1",
            PGPLAN_OUT=str(result_dir),
            HARNESS_EXIT_CODE="23",
        )

        self.assertEqual(result.returncode, 23, result.stdout)
        self.assertIn("Comparison corpus finished with failures (exit status 23", result.stdout)
        self.assertNotIn("All done!", result.stdout)
        for filename in (
            "status.tsv",
            "comparison.tsv",
            "comparison.csv",
            "comparison.log",
            "summary.tsv",
            "failures.tsv",
        ):
            self.assertIn(str(result_dir / filename), result.stdout)
        self.assertIn(f"Comparison result directory: {result_dir}", result.stdout)

    def test_reuse_from_is_forwarded_as_the_one_parameter_fast_mode(self) -> None:
        prior = self.repo / "prior corpus"
        result_dir = self.repo / "reuse-results"
        result = self._run(
            "--reuse-from",
            str(prior),
            RUN_PGPLAN="1",
            PGPLAN_OUT=str(result_dir),
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        call = self.log.read_text(encoding="utf-8").strip()
        self.assertIn(f"--reuse-from {prior}", call)
        self.assertIn(
            f"Reusing PGPlan artifacts and sealed target correctness from {prior} "
            "(PostgreSQL setup skipped)",
            result.stdout,
        )
        self.assertIn("Reuse mode: preserving existing DuckDB binary", result.stdout)

    def test_reuse_from_alone_auto_skips_build_data_and_query_generation(self) -> None:
        prior = self.repo / "prior-corpus"
        result = self._run(
            "--reuse-from",
            str(prior),
            RUN_PGPLAN="1",
            _inject_default_skips="0",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Step 1/5: Skipping build (SKIP_BUILD=1)", result.stdout)
        self.assertIn("Step 2/5: Skipping data build (SKIP_DATA=1)", result.stdout)
        self.assertIn(
            "Step 3/5: Skipping benchmark generation (SKIP_QUERY_GEN=1)",
            result.stdout,
        )
        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("corpus\t"), calls)

    def test_environment_reuse_from_is_forwarded(self) -> None:
        prior = self.repo / "prior-env-corpus"
        result = self._run(RUN_PGPLAN="1", PGPLAN_REUSE_FROM=str(prior))
        self.assertEqual(result.returncode, 0, result.stdout)
        call = self.log.read_text(encoding="utf-8").strip()
        self.assertIn(f"--reuse-from {prior}", call)

    def test_comparison_alias_and_plan_cache_are_forwarded(self) -> None:
        cache = self.repo / "persistent plan cache"
        result = self._run(
            "--skip1", "--plan-cache", str(cache), RUN_PGPLAN="1"
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        call = self.log.read_text(encoding="utf-8").strip()
        self.assertIn("--comparison-mode both", call)
        self.assertIn(f"--plan-cache {self.repo / 'auto_test/pgplan/plans'}", call)
        self.assertIn("--skip1", call)
        self.assertIn(f"--plan-cache {cache}", call)
        self.assertIn("Comparison mode=pgplan-only", result.stdout)

    def test_reuse_rejects_explicit_rebuild_request(self) -> None:
        prior = self.repo / "prior-corpus"
        result = self._run(
            "--reuse-from", str(prior), RUN_PGPLAN="1", SKIP_BUILD="0"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "SKIP_BUILD=0 conflicts with --reuse-from",
            result.stdout,
        )
        self.assertFalse(self.log.exists())

    def test_reuse_rejects_explicit_data_or_query_regeneration(self) -> None:
        prior = self.repo / "prior-corpus"
        for variable in ("SKIP_DATA", "SKIP_QUERY_GEN"):
            with self.subTest(variable=variable):
                if self.log.exists():
                    self.log.unlink()
                result = self._run(
                    "--reuse-from",
                    str(prior),
                    RUN_PGPLAN="1",
                    **{variable: "0"},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"{variable}=0 conflicts with --reuse-from",
                    result.stdout,
                )
                self.assertFalse(self.log.exists())

    def test_forwarded_out_path_is_used_for_the_final_handoff(self) -> None:
        environment_out = self.repo / "environment-results"
        command_line_out = self.repo / "command-line-results"
        result = self._run(
            "--out",
            str(command_line_out),
            RUN_PGPLAN="1",
            PGPLAN_OUT=str(environment_out),
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((command_line_out / "status.tsv").is_file())
        self.assertFalse(environment_out.exists())
        self.assertIn(
            f"Comparison result directory: {command_line_out}", result.stdout
        )
        self.assertNotIn(
            f"Comparison result directory: {environment_out}", result.stdout
        )

    def test_explicit_zero_preserves_two_way_corpus_run(self) -> None:
        result = self._run("--limit", "1", RUN_PGPLAN="0")
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("onoff\t"))
        self.assertIn("PGPlan disabled", result.stdout)

    def test_explicit_custom_corpus_is_preserved_across_config_source(self) -> None:
        custom_corpus = self.repo / "custom corpus"
        custom_corpus.mkdir()
        result = self._run(
            "--limit",
            "1",
            RUN_PGPLAN="0",
            OY_CORPUS=str(custom_corpus),
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        call = self.log.read_text(encoding="utf-8").strip()
        fields = call.split("\t", 2)
        self.assertEqual(fields[0], "onoff")
        self.assertEqual(fields[1], str(custom_corpus))
        self.assertIn("--only all", fields[2])


if __name__ == "__main__":
    unittest.main()
