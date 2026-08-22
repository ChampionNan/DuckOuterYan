#!/usr/bin/env python3
"""Focused wiring tests for run_all.sh's corpus-wide PGPlan stage."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


SOURCE_RUN_ALL = Path(__file__).resolve().parents[1] / "run_all.sh"


class RunAllPGPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name) / "repo"
        self.auto_test = self.repo / "auto_test"
        self.pgplan = self.auto_test / "pgplan"
        self.pgplan.mkdir(parents=True)
        (self.auto_test / "outerjoin_benchmark" / "benchmark").mkdir(parents=True)
        (self.auto_test / "outerjoin_query").symlink_to("outerjoin_benchmark/benchmark")
        (self.auto_test / "outerjoin_benchmark" / "industry_inspired" / "tpch").mkdir(
            parents=True
        )

        shutil.copy2(SOURCE_RUN_ALL, self.auto_test / "run_all.sh")
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
            export RUN_PGPLAN="${{RUN_PGPLAN:-1}}"
            export PGPLAN_QUERY="${{PGPLAN_QUERY:-{self.query}}}"
            export PGPLAN_EXECUTION_DB="${{PGPLAN_EXECUTION_DB:-$TPCH_DB}}"
            export PGPLAN_RUNS="${{PGPLAN_RUNS:-$OY_RUNS}}"
            export PGPLAN_THREADS="${{PGPLAN_THREADS:-$OY_THREADS}}"
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
            printf 'corpus\t%s\t%s\n' "${SKIP_PG_DATA:-unset}" "$args" >> "$HARNESS_LOG"
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
        env = os.environ.copy()
        for name in (
            "DUCKDB_BIN",
            "OY_CONFIG_LOADED",
            "OY_CORPUS",
            "RUN_PGPLAN",
            "RUN_PG_REPLAY",
            "PGPLAN_QUERY",
            "PGPLAN_EXECUTION_DB",
            "PGPLAN_RUNS",
            "PGPLAN_THREADS",
            "PGPLAN_TIMEOUT_SECS",
            "PGPLAN_TIMEOUT_GRACE",
            "PGPLAN_TMPDIR",
            "PGPLAN_OUT",
            "PGPLAN_PLAN_OUT",
            "PG_REPLAY_QUERY",
            "PG_REPLAY_EXECUTION_DB",
            "PG_REPLAY_RUNS",
            "PG_REPLAY_THREADS",
            "PG_REPLAY_TIMEOUT_SECS",
            "PG_REPLAY_TIMEOUT_GRACE",
            "PG_REPLAY_TMPDIR",
            "PG_REPLAY_OUT",
            "PG_REPLAY_PLAN_OUT",
        ):
            env.pop(name, None)
        env.update(
            {
                "HARNESS_LOG": str(self.log),
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

    def test_default_runs_corpus_wide_three_way_experiment(self) -> None:
        cli_duckdb = self.repo / "cli-duckdb"
        cli_duckdb.touch()
        cli_duckdb.chmod(0o755)
        result = self._run(
            "--bin",
            str(cli_duckdb),
            "--runs",
            "5",
            "--timeout",
            "12",
            "--only",
            "tpch",
        )
        self.assertEqual(result.returncode, 0, result.stdout)

        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1)
        fields = calls[0].split("\t", 2)
        self.assertEqual(fields[0], "corpus")
        # SKIP_DATA must not silently disable loading PG's independent tiny data.
        self.assertEqual(fields[1], "unset")
        corpus_args = fields[2]
        self.assertIn(f"--corpus {self.auto_test / 'outerjoin_query'}", corpus_args)
        self.assertIn(f"--duckdb-bin {self.duckdb}", corpus_args)
        self.assertIn("--rows 1000", corpus_args)
        self.assertIn("--threads 7", corpus_args)
        self.assertIn(f"--bin {cli_duckdb}", corpus_args)
        self.assertIn("--runs 5", corpus_args)
        self.assertIn("--timeout 12", corpus_args)
        self.assertIn("--only tpch", corpus_args)
        self.assertIn("Three-way status summary:", result.stdout)

    def test_escape_hatch_preserves_legacy_corpus_run(self) -> None:
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
