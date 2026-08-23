#!/usr/bin/env python3

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS = REPO_ROOT / "auto_test" / "configs.sh"


class PGPlanConfigTest(unittest.TestCase):
    def load_config(self, **overrides):
        names = [
            "OY_CONFIG_LOADED",
            "OY_REPO_ROOT",
            "DUCKDB_BIN",
            "TPCH_DB",
            "OY_RUNS",
            "OY_THREADS",
            "OY_TIMEOUT_SECS",
            "OY_BATCH_GRACE_SECS",
            "OY_TMPDIR",
            "RUN_PGPLAN",
            "PGPLAN_SETUP",
            "PGPLAN_VERSION",
            "PGPLAN_VERSION_NUM",
            "PGPLAN_ROOT",
            "PGPLAN_SOURCE_DIR",
            "PGPLAN_INSTALL_DIR",
            "PGPLAN_DATA_DIR",
            "PGPLAN_HOST",
            "PGPLAN_PORT",
            "PGPLAN_DATABASE",
            "PGPLAN_USER",
            "PGPLAN_PASSWORD",
            "PGPLAN_PASSWORD_FILE",
            "PGPLAN_CONTAINER_PASSWORD",
            "PGPLAN_QUERY",
            "PGPLAN_EXECUTION_DB",
            "PGPLAN_CORRECTNESS_GRAPH_ROWS",
            "PGPLAN_CORRECTNESS_JOB_ROWS",
            "PGPLAN_CORRECTNESS_MAX_RESULT_ROWS",
            "PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS",
            "PGPLAN_RUNS",
            "PGPLAN_THREADS",
            "PGPLAN_CAPTURE_TIMEOUT_SECS",
            "PGPLAN_TIMEOUT_SECS",
            "PGPLAN_TIMEOUT_GRACE",
            "PGPLAN_TMPDIR",
            "PGPLAN_FORCE_DATA",
            "RUN_PG_REPLAY",
            "PG_REPLAY_SETUP",
            "PG_REPLAY_VERSION",
            "PG_REPLAY_VERSION_NUM",
            "PG_REPLAY_ROOT",
            "PG_REPLAY_SOURCE_DIR",
            "PG_REPLAY_INSTALL_DIR",
            "PG_REPLAY_DATA_DIR",
            "PG_REPLAY_HOST",
            "PG_REPLAY_PORT",
            "PG_REPLAY_DATABASE",
            "PG_REPLAY_USER",
            "PG_REPLAY_PASSWORD",
            "PG_REPLAY_CONTAINER_PASSWORD",
            "PG_REPLAY_QUERY",
            "PG_REPLAY_EXECUTION_DB",
            "PG_REPLAY_CORRECTNESS_GRAPH_ROWS",
            "PG_REPLAY_CORRECTNESS_JOB_ROWS",
            "PG_REPLAY_CORRECTNESS_MAX_RESULT_ROWS",
            "PG_REPLAY_CORRECTNESS_QUERY_TIMEOUT_SECS",
            "PG_REPLAY_RUNS",
            "PG_REPLAY_THREADS",
            "PG_REPLAY_CAPTURE_TIMEOUT_SECS",
            "PG_REPLAY_TIMEOUT_SECS",
            "PG_REPLAY_TIMEOUT_GRACE",
            "PG_REPLAY_TMPDIR",
            "PG_REPLAY_FORCE_DATA",
            "PG_DSN",
            "PSQL_BIN",
            "PGPASSWORD",
        ]
        env = os.environ.copy()
        for name in names:
            env.pop(name, None)
        env.update({key: str(value) for key, value in overrides.items()})
        shell = """
source "$1"
for name in RUN_PGPLAN PGPLAN_SETUP PGPLAN_VERSION PGPLAN_VERSION_NUM \
    PGPLAN_ROOT PGPLAN_SOURCE_DIR PGPLAN_INSTALL_DIR PGPLAN_DATA_DIR \
    PGPLAN_HOST PGPLAN_PORT PGPLAN_DATABASE PGPLAN_USER PGPLAN_PASSWORD PGPLAN_PASSWORD_FILE \
    PGPLAN_CONTAINER_PASSWORD PG_REPLAY_PASSWORD PG_REPLAY_CONTAINER_PASSWORD PG_DSN PSQL_BIN \
    PGPASSWORD PGPLAN_QUERY PGPLAN_EXECUTION_DB PGPLAN_CORRECTNESS_GRAPH_ROWS \
    PGPLAN_CORRECTNESS_JOB_ROWS PGPLAN_CORRECTNESS_MAX_RESULT_ROWS \
    PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS PGPLAN_RUNS PGPLAN_THREADS \
    PGPLAN_CAPTURE_TIMEOUT_SECS PGPLAN_TIMEOUT_SECS PGPLAN_TIMEOUT_GRACE \
    PGPLAN_TMPDIR PGPLAN_FORCE_DATA PG_REPLAY_CAPTURE_TIMEOUT_SECS \
    PG_REPLAY_CORRECTNESS_GRAPH_ROWS PG_REPLAY_CORRECTNESS_JOB_ROWS \
    PG_REPLAY_CORRECTNESS_MAX_RESULT_ROWS PG_REPLAY_CORRECTNESS_QUERY_TIMEOUT_SECS \
    RUN_PG_REPLAY PG_REPLAY_SETUP PG_REPLAY_QUERY PG_REPLAY_FORCE_DATA; do
    printf '%s=%s\n' "$name" "${!name-}"
done
"""
        result = subprocess.run(
            ["bash", "-c", shell, "bash", str(CONFIGS)],
            text=True,
            capture_output=True,
            env=env,
            check=True,
        )
        return dict(line.split("=", 1) for line in result.stdout.splitlines())

    def test_source_defaults_match_repository_local_quorion_layout(self):
        values = self.load_config()
        pg_root = REPO_ROOT / "postgres"
        prefix = pg_root / "postgresql"
        self.assertEqual(values["RUN_PGPLAN"], "1")
        self.assertEqual(values["PGPLAN_SETUP"], "source")
        self.assertEqual(values["PGPLAN_VERSION"], "16.2")
        self.assertEqual(values["PGPLAN_VERSION_NUM"], "160002")
        self.assertEqual(values["PGPLAN_ROOT"], str(pg_root))
        self.assertEqual(values["PGPLAN_SOURCE_DIR"], str(pg_root))
        self.assertEqual(values["PGPLAN_INSTALL_DIR"], str(prefix))
        self.assertEqual(values["PGPLAN_DATA_DIR"], str(prefix / "data"))
        self.assertEqual(values["PSQL_BIN"], str(prefix / "bin" / "psql"))
        self.assertRegex(values["PGPASSWORD"], r"^[0-9a-f]{64}$")
        password_file = Path(values["PGPLAN_PASSWORD_FILE"])
        self.assertEqual(password_file, prefix / ".pgplan-password")
        self.assertEqual(password_file.read_text(encoding="utf-8").strip(), values["PGPASSWORD"])
        self.assertEqual(password_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            values["PGPLAN_QUERY"],
            str(
                REPO_ROOT
                / "auto_test/outerjoin_benchmark/industry_inspired/tpch"
                / "oy_th_real_supplier_right.sql"
            ),
        )
        self.assertEqual(values["PGPLAN_EXECUTION_DB"], str(REPO_ROOT / "tpch_db"))
        self.assertEqual(values["PGPLAN_CORRECTNESS_GRAPH_ROWS"], "500")
        self.assertEqual(values["PGPLAN_CORRECTNESS_JOB_ROWS"], "1000")
        self.assertEqual(values["PGPLAN_CORRECTNESS_MAX_RESULT_ROWS"], "2000000")
        self.assertEqual(values["PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS"], "30")
        self.assertEqual(
            values["PG_REPLAY_CORRECTNESS_GRAPH_ROWS"],
            values["PGPLAN_CORRECTNESS_GRAPH_ROWS"],
        )
        self.assertEqual(values["PGPLAN_CAPTURE_TIMEOUT_SECS"], "60")
        self.assertEqual(
            values["PG_REPLAY_CAPTURE_TIMEOUT_SECS"],
            values["PGPLAN_CAPTURE_TIMEOUT_SECS"],
        )
        self.assertEqual(values["PGPLAN_FORCE_DATA"], "0")
        self.assertEqual(values["RUN_PG_REPLAY"], values["RUN_PGPLAN"])
        self.assertEqual(values["PG_REPLAY_SETUP"], values["PGPLAN_SETUP"])
        self.assertEqual(values["PG_REPLAY_QUERY"], values["PGPLAN_QUERY"])
        self.assertEqual(values["PG_REPLAY_FORCE_DATA"], values["PGPLAN_FORCE_DATA"])

    def test_pgplan_timing_defaults_follow_main_harness(self):
        values = self.load_config(
            OY_RUNS=5,
            OY_THREADS=12,
            OY_TIMEOUT_SECS=99,
            OY_BATCH_GRACE_SECS=7,
            OY_TMPDIR="/tmp/duckyan-test",
            PGPLAN_CAPTURE_TIMEOUT_SECS=17,
        )
        self.assertEqual(values["PGPLAN_RUNS"], "5")
        self.assertEqual(values["PGPLAN_THREADS"], "12")
        self.assertEqual(values["PGPLAN_CAPTURE_TIMEOUT_SECS"], "17")
        self.assertEqual(values["PGPLAN_TIMEOUT_SECS"], "99")
        self.assertEqual(values["PGPLAN_TIMEOUT_GRACE"], "7")
        self.assertEqual(values["PGPLAN_TMPDIR"], "/tmp/duckyan-test")

    def test_source_mode_ignores_an_unrelated_ambient_libpq_password(self):
        values = self.load_config(PGPASSWORD="stale-ambient-password")
        self.assertRegex(values["PGPASSWORD"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(values["PGPASSWORD"], "stale-ambient-password")

    def test_docker_mode_uses_repository_wrapper_and_preserves_overrides(self):
        values = self.load_config(
            PGPLAN_SETUP="docker",
            PG_DSN="host=custom dbname=plans",
            PGPLAN_CONTAINER_PASSWORD="custom-password",
        )
        self.assertEqual(values["PG_DSN"], "host=custom dbname=plans")
        self.assertEqual(values["PGPASSWORD"], "custom-password")
        self.assertEqual(
            values["PSQL_BIN"],
            str(REPO_ROOT / "auto_test/pgplan/docker_psql.sh"),
        )

    def test_docker_mode_uses_the_private_managed_password_by_default(self):
        values = self.load_config(PGPLAN_SETUP="docker", PGPASSWORD="stale")
        self.assertRegex(values["PGPASSWORD"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            Path(values["PGPLAN_PASSWORD_FILE"]).read_text(encoding="utf-8").strip(),
            values["PGPASSWORD"],
        )

    def test_empty_managed_password_overrides_generate_a_private_secret(self):
        for setup in ("source", "docker"):
            with self.subTest(setup=setup), tempfile.TemporaryDirectory() as temporary:
                prefix = Path(temporary) / "postgresql"
                values = self.load_config(
                    PGPLAN_SETUP=setup,
                    PGPLAN_INSTALL_DIR=prefix,
                    PGPLAN_PASSWORD="",
                    PG_REPLAY_PASSWORD="",
                    PGPLAN_CONTAINER_PASSWORD="",
                    PG_REPLAY_CONTAINER_PASSWORD="",
                )
                self.assertRegex(values["PGPLAN_PASSWORD"], r"^[0-9a-f]{64}$")
                self.assertNotEqual(values["PGPLAN_PASSWORD"], "duckyan")
                self.assertEqual(values["PGPASSWORD"], values["PGPLAN_PASSWORD"])
                self.assertEqual(
                    values["PG_REPLAY_PASSWORD"], values["PGPLAN_PASSWORD"]
                )
                self.assertEqual(
                    values["PGPLAN_CONTAINER_PASSWORD"], values["PGPLAN_PASSWORD"]
                )
                self.assertEqual(
                    values["PG_REPLAY_CONTAINER_PASSWORD"],
                    values["PGPLAN_PASSWORD"],
                )
                self.assertEqual(
                    Path(values["PGPLAN_PASSWORD_FILE"])
                    .read_text(encoding="utf-8")
                    .strip(),
                    values["PGPLAN_PASSWORD"],
                )

    def test_nonempty_legacy_managed_password_overrides_empty_new_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = Path(temporary) / "postgresql"
            source = self.load_config(
                PGPLAN_SETUP="source",
                PGPLAN_INSTALL_DIR=prefix,
                PGPLAN_PASSWORD="",
                PG_REPLAY_PASSWORD="legacy-source-secret",
            )
            self.assertEqual(source["PGPLAN_PASSWORD"], "legacy-source-secret")
            self.assertEqual(source["PGPASSWORD"], "legacy-source-secret")
            self.assertFalse(Path(source["PGPLAN_PASSWORD_FILE"]).exists())

            docker = self.load_config(
                PGPLAN_SETUP="docker",
                PGPLAN_INSTALL_DIR=prefix,
                PGPLAN_PASSWORD="",
                PG_REPLAY_PASSWORD="",
                PGPLAN_CONTAINER_PASSWORD="",
                PG_REPLAY_CONTAINER_PASSWORD="legacy-docker-secret",
            )
            self.assertEqual(docker["PGPLAN_PASSWORD"], "legacy-docker-secret")
            self.assertEqual(docker["PGPLAN_CONTAINER_PASSWORD"], "legacy-docker-secret")
            self.assertEqual(docker["PGPASSWORD"], "legacy-docker-secret")
            self.assertFalse(Path(docker["PGPLAN_PASSWORD_FILE"]).exists())

    def test_external_mode_retains_its_historical_empty_override_behavior(self):
        values = self.load_config(
            PGPLAN_SETUP="external",
            PGPLAN_PASSWORD="",
            PG_REPLAY_PASSWORD="",
            PGPLAN_CONTAINER_PASSWORD="",
            PG_REPLAY_CONTAINER_PASSWORD="",
        )
        self.assertEqual(values["PGPLAN_PASSWORD"], "duckyan")
        self.assertEqual(values["PGPASSWORD"], "")

    def test_verbose_external_config_does_not_log_dsn_credentials(self):
        env = os.environ.copy()
        env.pop("OY_CONFIG_LOADED", None)
        env.update(
            {
                "OY_CONFIG_VERBOSE": "1",
                "PGPLAN_SETUP": "external",
                "PG_DSN": "host=db.example password=do-not-log dbname=plans",
            }
        )
        result = subprocess.run(
            ["bash", "-c", 'source "$1"', "bash", str(CONFIGS)],
            text=True,
            capture_output=True,
            env=env,
            check=True,
        )
        self.assertNotIn("do-not-log", result.stderr)
        self.assertIn("external PG_DSN (redacted)", result.stderr)

    def test_legacy_environment_names_are_compatibility_aliases(self):
        values = self.load_config(
            RUN_PG_REPLAY="0",
            PG_REPLAY_SETUP="docker",
            PG_REPLAY_QUERY="/tmp/legacy-query.sql",
        )
        self.assertEqual(values["RUN_PGPLAN"], "0")
        self.assertEqual(values["PGPLAN_SETUP"], "docker")
        self.assertEqual(values["PGPLAN_QUERY"], "/tmp/legacy-query.sql")


if __name__ == "__main__":
    unittest.main()
