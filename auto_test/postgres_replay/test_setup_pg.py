#!/usr/bin/env python3

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SETUP_PG = SCRIPT_DIR / "setup_pg.sh"
DOCKER_PSQL = SCRIPT_DIR / "docker_psql.sh"
PREPARE_PG = SCRIPT_DIR / "prepare_tpch_pg.sh"


FAKE_PSQL = r"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${FAKE_PSQL_LOG:?}"
case "${PGPASSWORD:-}" in
    *.pgplan-invalid-probe) exit 1 ;;
esac
for argument in "$@"; do
    case "$argument" in
        --file=*)
            grep -q 'ALTER ROLE' "${argument#--file=}" || exit 69
            exit 0
            ;;
    esac
done
case "$*" in
    *server_version_num*) printf '%s\n' "${FAKE_PG_VERSION:-160002}" ;;
    *data_directory*) printf '%s\n' "${FAKE_DATA_DIRECTORY:?}" ;;
    *pg_hba_file_rules*) printf '0\n' ;;
    *'SELECT 1;'*) printf '1\n' ;;
    *pg_database*) printf '1\n' ;;
    *to_regclass*) printf '%s\n' "${FAKE_TABLE_COUNT:-8}" ;;
    *'count(*) FROM public.region'*) printf '%s\n' "${FAKE_CARDINALITIES:-5|25|100|1500|2000|8000|15000|60175}" ;;
    *ANALYZE*) : ;;
    *) printf 'unexpected fake psql invocation: %s\n' "$*" >&2; exit 70 ;;
esac
"""


class SetupPostgresTest(unittest.TestCase):
    def make_executable(self, path, contents):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(contents), encoding="utf-8")
        path.chmod(0o755)

    def source_environment(self, root, **overrides):
        install = root / "install"
        data = install / "data"
        data.mkdir(parents=True)
        (data / "PG_VERSION").write_text("16\n", encoding="utf-8")
        self.make_executable(
            install / "bin/postgres",
            """\
            #!/usr/bin/env bash
            echo 'postgres (PostgreSQL) 16.2'
            """,
        )
        self.make_executable(
            install / "bin/pg_ctl",
            """\
            #!/usr/bin/env bash
            case "${*: -1}" in status|reload) exit 0 ;; esac
            exit 71
            """,
        )
        for name in ("initdb", "createdb"):
            self.make_executable(
                install / f"bin/{name}",
                f"#!/usr/bin/env bash\necho '{name} must not run' >&2\nexit 72\n",
            )
        (data / "pg_hba.conf").write_text(
            "local all all trust\n"
            "host all all 127.0.0.1/32 trust\n"
            "host all all ::1/128 trust\n",
            encoding="utf-8",
        )
        fake_psql = root / "fake-psql"
        self.make_executable(fake_psql, FAKE_PSQL)
        fake_duckdb = root / "fake-duckdb"
        self.make_executable(fake_duckdb, "#!/usr/bin/env bash\nexit 73\n")
        env = os.environ.copy()
        env.update(
            {
                "OY_CONFIG_LOADED": "",
                "PGPLAN_SETUP": "source",
                "PGPLAN_SOURCE_DIR": str(root / "source"),
                "PGPLAN_INSTALL_DIR": str(install),
                "PGPLAN_DATA_DIR": str(data),
                "PGPLAN_LOG_FILE": str(install / "postgres.log"),
                "PGPLAN_HOST": "127.0.0.1",
                "PGPLAN_PORT": "55432",
                "PGPLAN_DATABASE": "duckyan_tpch",
                "PGPLAN_USER": "postgres",
                "PG_DSN": "host=127.0.0.1 port=55432 dbname=duckyan_tpch user=postgres",
                "PSQL_BIN": str(fake_psql),
                "DUCKDB_BIN": str(fake_duckdb),
                "FAKE_PSQL_LOG": str(root / "psql.log"),
                "FAKE_DATA_DIRECTORY": str(data),
            }
        )
        env.update({key: str(value) for key, value in overrides.items()})
        return env

    def test_source_mode_reuses_running_server_and_verified_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = self.source_environment(root)
            result = subprocess.run(
                ["bash", str(SETUP_PG)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("reusing verified TPC-H SF0.01 data", result.stdout)
            self.assertIn("setup ready: mode=source PostgreSQL=160002", result.stdout)
            self.assertIn("ANALYZE public.region", (root / "psql.log").read_text())
            hba = (root / "install/data/pg_hba.conf").read_text(encoding="utf-8")
            self.assertNotIn(" trust", hba)
            self.assertIn("peer", hba)
            self.assertIn("scram-sha-256", hba)

    def test_new_source_cluster_uses_peer_and_scram_from_initdb(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = self.source_environment(root)
            data = root / "install/data"
            shutil.rmtree(data)
            initdb_log = root / "initdb.log"
            env["FAKE_INITDB_LOG"] = str(initdb_log)
            self.make_executable(
                root / "install/bin/initdb",
                r"""\
                #!/usr/bin/env bash
                set -euo pipefail
                printf '%s\n' "$@" > "${FAKE_INITDB_LOG:?}"
                data=""
                pwfile=""
                for argument in "$@"; do
                    case "$argument" in
                        -D) expect_data=1 ;;
                        --pwfile=*) pwfile="${argument#--pwfile=}" ;;
                        *)
                            if [ "${expect_data:-0}" = 1 ]; then
                                data="$argument"
                                expect_data=0
                            fi
                            ;;
                    esac
                done
                [ -n "$data" ] && [ -s "$pwfile" ]
                grep -qx -- '--auth-local=peer' "${FAKE_INITDB_LOG:?}"
                grep -qx -- '--auth-host=scram-sha-256' "${FAKE_INITDB_LOG:?}"
                mkdir -p "$data"
                printf '16\n' > "$data/PG_VERSION"
                printf 'local all all peer\nhost all all 127.0.0.1/32 scram-sha-256\n' \
                    > "$data/pg_hba.conf"
                """,
            )
            result = subprocess.run(
                ["bash", str(SETUP_PG)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            initdb_args = initdb_log.read_text(encoding="utf-8")
            self.assertIn("--auth-local=peer", initdb_args)
            self.assertIn("--auth-host=scram-sha-256", initdb_args)
            self.assertIn("--pwfile=", initdb_args)
            self.assertEqual(list((root / "install").glob(".pgplan-initdb-password.*")), [])

    def test_source_mode_does_not_log_the_managed_password(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = "source-secret-do-not-log"
            env = self.source_environment(root, PGPLAN_PASSWORD=secret)
            result = subprocess.run(
                ["bash", str(SETUP_PG)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(secret, result.stdout)
            self.assertNotIn(secret, result.stderr)

    def test_skip_data_still_rejects_an_unverified_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = self.source_environment(root, SKIP_PG_DATA="1", FAKE_TABLE_COUNT="0")
            result = subprocess.run(
                ["bash", str(SETUP_PG)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("SKIP_PG_DATA=1 requires existing TPC-H SF0.01", result.stderr)

    def test_source_mode_rejects_a_different_server_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            other_data = root / "other-data"
            other_data.mkdir()
            env = self.source_environment(root, FAKE_DATA_DIRECTORY=str(other_data))
            result = subprocess.run(
                ["bash", str(SETUP_PG)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("configured source endpoint belongs to", result.stderr)
            self.assertIn(
                " trust", (root / "install/data/pg_hba.conf").read_text(encoding="utf-8")
            )

    def test_managed_mode_rejects_a_raw_dsn_redirect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = self.source_environment(root, PG_DSN="host=other dbname=postgres")
            result = subprocess.run(
                ["bash", str(SETUP_PG)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("requires the configs.sh-derived PG_DSN", result.stderr)

    def test_source_mode_rejects_a_non_loopback_bind_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = self.source_environment(
                root,
                PGPLAN_HOST="0.0.0.0",
                PG_DSN="host=0.0.0.0 port=55432 dbname=duckyan_tpch user=postgres",
            )
            result = subprocess.run(
                ["bash", str(SETUP_PG)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("requires a loopback PGPLAN_HOST", result.stderr)
            self.assertFalse((root / "psql.log").exists())

    def test_external_partial_data_is_not_replaced_implicitly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = self.source_environment(
                root, PGPLAN_SETUP="external", FAKE_TABLE_COUNT="2"
            )
            result = subprocess.run(
                ["bash", str(SETUP_PG)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("external database has incomplete", result.stderr)

    def test_external_success_does_not_log_dsn_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = "do-not-log"
            env = self.source_environment(
                root,
                PGPLAN_SETUP="external",
                PG_DSN=f"host=fake dbname=duckyan_tpch password={secret}",
            )
            result = subprocess.run(
                ["bash", str(SETUP_PG)],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(secret, result.stdout)
            self.assertNotIn(secret, result.stderr)
            self.assertIn("external PG_DSN validated (redacted)", result.stdout)


class DockerPsqlTest(unittest.TestCase):
    def test_host_sql_file_is_streamed_to_container_psql(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            log = root / "docker.log"
            stdin_log = root / "stdin.sql"
            docker = fake_bin / "docker"
            docker.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    if [ "$1" = inspect ]; then
                        exit 0
                    fi
                    {
                        printf '%s\n' "$@"
                        printf 'env=%s\n' "${PGPASSWORD:-}"
                    } > "${FAKE_DOCKER_LOG:?}"
                    cat > "${FAKE_DOCKER_STDIN:?}"
                    """
                ),
                encoding="utf-8",
            )
            docker.chmod(0o755)
            sql_file = root / "capture.sql"
            sql_file.write_text("SELECT 42;\n", encoding="utf-8")
            env = os.environ.copy()
            env.update(
                {
                    "OY_CONFIG_LOADED": "",
                    "PATH": f"{fake_bin}:{env.get('PATH', '')}",
                    "PGPLAN_SETUP": "docker",
                    "PGPLAN_CONTAINER_NAME": "fake-pg",
                    "PGPLAN_CONTAINER_DATABASE": "plans",
                    "PGPLAN_CONTAINER_USER": "planner",
                    "PGPLAN_CONTAINER_PASSWORD": "secret",
                    "FAKE_DOCKER_LOG": str(log),
                    "FAKE_DOCKER_STDIN": str(stdin_log),
                }
            )
            result = subprocess.run(
                [
                    "bash",
                    str(DOCKER_PSQL),
                    "-X",
                    "--dbname=host=ignored port=55432 dbname=ignored",
                    f"--file={sql_file}",
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            args = log.read_text(encoding="utf-8")
            self.assertIn("exec\n-i\n--env\nPGPASSWORD\nfake-pg\npsql\n", args)
            self.assertIn("env=secret", args)
            self.assertNotIn("PGPASSWORD=secret", args)
            self.assertIn("host=/var/run/postgresql port=5432 dbname=plans user=planner", args)
            self.assertIn("--file=-", args)
            self.assertNotIn(str(sql_file), args)
            self.assertEqual(stdin_log.read_text(encoding="utf-8"), "SELECT 42;\n")


class ManagedDockerSetupTest(unittest.TestCase):
    def run_setup(self, configured_password, expected_password):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        docker_log = root / "docker.log"
        docker = fake_bin / "docker"
        docker.write_text(
            textwrap.dedent(
                r"""\
                #!/usr/bin/env bash
                set -euo pipefail
                printf '%s|env=%s\n' "$*" "${PGPASSWORD:-}" >> "${FAKE_DOCKER_LOG:?}"
                case "$1" in
                    inspect)
                        case "$*" in *State.Running*) printf 'true\n' ;; esac
                        ;;
                    exec)
                        shift
                        if [ "${1:-}" = -i ]; then shift; fi
                        if [ "${1:-}" = --env ]; then
                            [ "$2" = PGPASSWORD ]
                            shift 2
                        fi
                        [ "$1" = managed-pg ] || exit 81
                        shift
                        if [ "$1" = pg_isready ]; then exit 0; fi
                        [ "$1" = psql ] || exit 82
                        shift
                        case "${PGPASSWORD:-}" in
                            *.pgplan-invalid-probe) exit 2 ;;
                        esac
                        [ "${PGPASSWORD:-}" = "${FAKE_DOCKER_EXPECTED_PASSWORD:?}" ] || exit 3
                        case "$*" in
                            *server_version_num*) printf '160002\n' ;;
                            *to_regclass*) printf '8\n' ;;
                            *"count(*) FROM public.region"*) printf '5|25|100|1500|2000|8000|15000|60175\n' ;;
                            *'SELECT 1;'*) printf '1\n' ;;
                            *ANALYZE*) : ;;
                            *) : ;;
                        esac
                        ;;
                    *) exit 83 ;;
                esac
                """
            ),
            encoding="utf-8",
        )
        docker.chmod(0o755)
        fake_duckdb = root / "duckdb"
        fake_duckdb.write_text("#!/usr/bin/env bash\nexit 84\n", encoding="utf-8")
        fake_duckdb.chmod(0o755)
        env = os.environ.copy()
        for name in ("OY_CONFIG_LOADED", "PSQL_BIN", "PG_DSN", "PGPASSWORD"):
            env.pop(name, None)
        env.update(
            {
                "PATH": f"{fake_bin}:{env.get('PATH', '')}",
                "PGPLAN_SETUP": "docker",
                "PGPLAN_ROOT": str(root / "postgres"),
                "PGPLAN_INSTALL_DIR": str(root / "postgres/install"),
                "PGPLAN_CONTAINER_NAME": "managed-pg",
                "PGPLAN_CONTAINER_DATABASE": "plans",
                "PGPLAN_CONTAINER_USER": "planner",
                "PGPLAN_CONTAINER_PASSWORD": configured_password,
                "PGPLAN_DATABASE": "plans",
                "PGPLAN_USER": "planner",
                "PGPLAN_PORT": "55556",
                "DUCKDB_BIN": str(fake_duckdb),
                "FAKE_DOCKER_LOG": str(docker_log),
                "FAKE_DOCKER_EXPECTED_PASSWORD": expected_password,
            }
        )
        result = subprocess.run(
            ["bash", str(SETUP_PG), "--skip-data"],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        return temporary, docker_log, result

    def test_existing_container_accepts_configured_private_password(self):
        temporary, docker_log, result = self.run_setup("private-secret", "private-secret")
        try:
            self.assertEqual(result.returncode, 0, result.stderr)
            log = docker_log.read_text(encoding="utf-8")
            self.assertIn(
                "pg_isready --host=127.0.0.1 --port=5432", log
            )
            self.assertIn("--host=127.0.0.1", log)
            self.assertIn("env=private-secret", log)
            self.assertNotIn("PGPASSWORD=private-secret", log)
        finally:
            temporary.cleanup()

    def test_existing_container_with_old_password_fails_clearly(self):
        temporary, _, result = self.run_setup("new-private-secret", "old-secret")
        try:
            self.assertEqual(result.returncode, 2)
            self.assertIn("rejected the configured private password", result.stderr)
            self.assertIn("remove/recreate managed-pg", result.stderr)
        finally:
            temporary.cleanup()

    def test_fresh_container_waits_for_tcp_and_keeps_password_out_of_argv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            docker_args = root / "docker.args"
            docker_env = root / "docker.env"
            docker_state = root / "container.started"
            tcp_ready = root / "tcp.ready"
            docker = fake_bin / "docker"
            docker.write_text(
                textwrap.dedent(
                    r"""\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    printf '%s\n' "$*" >> "${FAKE_DOCKER_ARGS:?}"
                    printf 'post=%s pg=%s\n' "${POSTGRES_PASSWORD:-}" "${PGPASSWORD:-}" \
                        >> "${FAKE_DOCKER_ENV:?}"
                    case "$1" in
                        inspect)
                            [ -f "${FAKE_DOCKER_STATE:?}" ] || exit 1
                            case "$*" in *State.Running*) printf 'true\n' ;; esac
                            ;;
                        run)
                            [ "${POSTGRES_PASSWORD:-}" = "${FAKE_DOCKER_EXPECTED_PASSWORD:?}" ] || exit 85
                            case "$*" in
                                *"${FAKE_DOCKER_EXPECTED_PASSWORD}"*) exit 86 ;;
                            esac
                            : > "${FAKE_DOCKER_STATE:?}"
                            printf 'fake-container-id\n'
                            ;;
                        exec)
                            shift
                            if [ "${1:-}" = -i ]; then shift; fi
                            if [ "${1:-}" = --env ]; then
                                [ "$2" = PGPASSWORD ]
                                shift 2
                            fi
                            [ "$1" = managed-pg ] || exit 87
                            shift
                            if [ "$1" = pg_isready ]; then
                                case " $* " in
                                    *" --host=127.0.0.1 "*) ;;
                                    *)
                                        # Model the official image's temporary socket-only
                                        # initialization server. It must not satisfy setup.
                                        exit 0
                                        ;;
                                esac
                                case " $* " in
                                    *" --port=5432 "*) ;;
                                    *) exit 92 ;;
                                esac
                                : > "${FAKE_DOCKER_TCP_READY:?}"
                                exit 0
                            fi
                            [ -f "${FAKE_DOCKER_TCP_READY:?}" ] || exit 88
                            [ "$1" = psql ] || exit 89
                            shift
                            case "${PGPASSWORD:-}" in
                                *.pgplan-invalid-probe) exit 2 ;;
                            esac
                            [ "${PGPASSWORD:-}" = "${FAKE_DOCKER_EXPECTED_PASSWORD:?}" ] || exit 3
                            case "$*" in
                                *server_version_num*) printf '160002\n' ;;
                                *to_regclass*) printf '8\n' ;;
                                *"count(*) FROM public.region"*) printf '5|25|100|1500|2000|8000|15000|60175\n' ;;
                                *'SELECT 1;'*) printf '1\n' ;;
                                *ANALYZE*) : ;;
                                *) : ;;
                            esac
                            ;;
                        *) exit 90 ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            docker.chmod(0o755)
            fake_duckdb = root / "duckdb"
            fake_duckdb.write_text("#!/usr/bin/env bash\nexit 91\n", encoding="utf-8")
            fake_duckdb.chmod(0o755)
            secret = "fresh-private-secret"
            env = os.environ.copy()
            for name in ("OY_CONFIG_LOADED", "PSQL_BIN", "PG_DSN", "PGPASSWORD"):
                env.pop(name, None)
            env.update(
                {
                    "PATH": f"{fake_bin}:{env.get('PATH', '')}",
                    "PGPLAN_SETUP": "docker",
                    "PGPLAN_ROOT": str(root / "postgres"),
                    "PGPLAN_INSTALL_DIR": str(root / "postgres/install"),
                    "PGPLAN_CONTAINER_NAME": "managed-pg",
                    "PGPLAN_CONTAINER_DATABASE": "plans",
                    "PGPLAN_CONTAINER_USER": "planner",
                    "PGPLAN_CONTAINER_PASSWORD": secret,
                    "PGPLAN_DATABASE": "plans",
                    "PGPLAN_USER": "planner",
                    "PGPLAN_PORT": "55556",
                    "DUCKDB_BIN": str(fake_duckdb),
                    "FAKE_DOCKER_ARGS": str(docker_args),
                    "FAKE_DOCKER_ENV": str(docker_env),
                    "FAKE_DOCKER_STATE": str(docker_state),
                    "FAKE_DOCKER_TCP_READY": str(tcp_ready),
                    "FAKE_DOCKER_EXPECTED_PASSWORD": secret,
                }
            )
            result = subprocess.run(
                ["bash", str(SETUP_PG), "--skip-data"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            args = docker_args.read_text(encoding="utf-8")
            docker_environment = docker_env.read_text(encoding="utf-8")
            self.assertEqual(
                result.returncode,
                0,
                f"{result.stderr}\nargs:\n{args}\nenvironment:\n{docker_environment}",
            )
            self.assertIn("--env POSTGRES_PASSWORD", args)
            self.assertIn("pg_isready --host=127.0.0.1 --port=5432", args)
            self.assertNotIn(secret, args)
            self.assertIn(f"post={secret}", docker_environment)
            self.assertTrue(tcp_ready.exists())


class DirectDockerPrepareTest(unittest.TestCase):
    def test_cli_container_name_is_forwarded_to_docker_psql_wrapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            docker_log = root / "docker.log"
            docker_state = root / "container.started"
            docker = fake_bin / "docker"
            docker.write_text(
                textwrap.dedent(
                    r"""\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    printf '%s\n' "$*" >> "${FAKE_DOCKER_LOG:?}"
                    case "$1" in
                        inspect)
                            [ -f "${FAKE_DOCKER_STATE:?}" ]
                            ;;
                        run)
                            : > "${FAKE_DOCKER_STATE:?}"
                            printf 'fake-container-id\n'
                            ;;
                        exec)
                            shift
                            if [ "${1:-}" = -i ]; then shift; fi
                            if [ "${1:-}" = --env ]; then shift 2; fi
                            container="$1"
                            shift
                            [ "$container" = custom-pg ] || exit 74
                            if [ "$1" = pg_isready ]; then exit 0; fi
                            [ "$1" = psql ] || exit 75
                            shift
                            command_line="$*"
                            case "$command_line" in
                                *server_version_num*) printf '160002\n' ;;
                                *to_regclass*) printf '0\n' ;;
                                *"count(*) FROM public.region"*) printf '5|25|100|1500|2000|8000|15000|60175\n' ;;
                                *"'part='"*) printf 'part=2000 supplier=100 partsupp=8000 lineitem=60175\n' ;;
                                *) : ;;
                            esac
                            ;;
                        *) exit 76 ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            docker.chmod(0o755)
            data = root / "tpch"
            data.mkdir()
            for table in (
                "region",
                "nation",
                "supplier",
                "customer",
                "part",
                "partsupp",
                "orders",
                "lineitem",
            ):
                (data / f"{table}.csv").write_text("", encoding="utf-8")

            env = os.environ.copy()
            env.pop("PSQL_BIN", None)
            env.update(
                {
                    "OY_CONFIG_LOADED": "",
                    "PATH": f"{fake_bin}:{env.get('PATH', '')}",
                    "PGPLAN_CONTAINER_DATABASE": "plans",
                    "PGPLAN_CONTAINER_USER": "planner",
                    "PGPLAN_CONTAINER_PASSWORD": "secret",
                    "FAKE_DOCKER_LOG": str(docker_log),
                    "FAKE_DOCKER_STATE": str(docker_state),
                }
            )
            result = subprocess.run(
                [
                    "bash",
                    str(PREPARE_PG),
                    "--local-container",
                    "--container-name",
                    "custom-pg",
                    "--port",
                    "55555",
                    "--data-dir",
                    str(data),
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            invocations = docker_log.read_text(encoding="utf-8")
            self.assertIn("--name custom-pg", invocations)
            self.assertIn("--env POSTGRES_PASSWORD", invocations)
            self.assertNotIn("POSTGRES_PASSWORD=secret", invocations)
            self.assertIn("--publish 127.0.0.1:55555:5432", invocations)
            self.assertIn(
                "pg_isready --host=127.0.0.1 --port=5432", invocations
            )
            self.assertNotIn("duckyan-pg16-2 psql", invocations)
            self.assertIn("custom-pg psql", invocations)


if __name__ == "__main__":
    unittest.main()
