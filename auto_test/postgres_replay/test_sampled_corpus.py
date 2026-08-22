#!/usr/bin/env python3
"""Focused tests for sampled family loading and corpus PGPlan orchestration."""

from __future__ import annotations

import csv
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_TOOL = SCRIPT_DIR / "schema_from_duckdb.py"
SAMPLED_LOADER = SCRIPT_DIR / "prepare_sampled_pg.sh"
CORPUS_RUNNER = SCRIPT_DIR / "corpus_experiment.sh"


class SchemaConversionTest(unittest.TestCase):
    def test_schema_conversion_preserves_nullability_and_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "columns.csv"
            constraints = root / "constraints.csv"
            output = root / "schema.sql"
            metadata.write_text(
                "table_name,column_name,data_type,is_nullable,ordinal_position\n"
                "Facts,id,UBIGINT,NO,1\n"
                'Facts,amount,"DECIMAL(15,2)",YES,2\n'
                "Dims,id,INTEGER,NO,1\n"
                "Dims,label,VARCHAR,YES,2\n",
                encoding="utf-8",
            )
            constraints.write_text(
                "table_name,constraint_index,constraint_type,column_name\n"
                "Facts,0,PRIMARY KEY,id\n"
                "Dims,0,UNIQUE,id\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "python3", str(SCHEMA_TOOL),
                    "--metadata", str(metadata),
                    "--constraints", str(constraints),
                    "--schema", "pgplan_test",
                    "--table", "facts",
                    "--table", "dims",
                    "--provenance", "unit test",
                    "--replace",
                    "--out", str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            sql = output.read_text(encoding="utf-8")
            self.assertIn('DROP SCHEMA IF EXISTS "pgplan_test" CASCADE;', sql)
            self.assertIn('"id" NUMERIC(20, 0) NOT NULL', sql)
            self.assertIn('"amount" NUMERIC(15, 2)', sql)
            self.assertIn('PRIMARY KEY ("id")', sql)
            self.assertIn('UNIQUE ("id")', sql)

    def test_unknown_duckdb_type_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "columns.csv"
            constraints = root / "constraints.csv"
            metadata.write_text(
                "table_name,column_name,data_type,is_nullable,ordinal_position\n"
                "x,payload,MAP(VARCHAR INTEGER),YES,1\n",
                encoding="utf-8",
            )
            constraints.write_text(
                "table_name,constraint_index,constraint_type,column_name\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "python3", str(SCHEMA_TOOL),
                    "--metadata", str(metadata),
                    "--constraints", str(constraints),
                    "--schema", "pgplan_test",
                    "--table", "x",
                    "--provenance", "unit test",
                    "--out", str(root / "schema.sql"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("unsupported DuckDB type", result.stderr)

    def test_job_reviewed_double_columns_become_documented_bigints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "columns.csv"
            constraints = root / "constraints.csv"
            output = root / "schema.sql"
            coercions = root / "coercions.tsv"
            metadata.write_text(
                "table_name,column_name,data_type,is_nullable,ordinal_position\n"
                "title,id,INTEGER,NO,1\n"
                "title,production_year,DOUBLE,YES,2\n"
                "title,imdb_id,DOUBLE,YES,3\n"
                "title,episode_of_id,DOUBLE,YES,4\n"
                "title,season_nr,DOUBLE,YES,5\n"
                "title,episode_nr,DOUBLE,YES,6\n",
                encoding="utf-8",
            )
            constraints.write_text(
                "table_name,constraint_index,constraint_type,column_name\n"
                "title,0,PRIMARY KEY,id\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "python3", str(SCHEMA_TOOL),
                    "--metadata", str(metadata),
                    "--constraints", str(constraints),
                    "--schema", "pgplan_job",
                    "--family", "job",
                    "--table", "title",
                    "--provenance", "unit test",
                    "--coercions-out", str(coercions),
                    "--out", str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            sql = output.read_text(encoding="utf-8")
            self.assertIn('"production_year" BIGINT', sql)
            self.assertIn("validated integral coercion", sql)
            with coercions.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source, delimiter="\t"))
            self.assertEqual(
                {row["column_name"] for row in rows},
                {"production_year", "imdb_id", "episode_of_id", "season_nr", "episode_nr"},
            )
            self.assertTrue(all(row["pg_type"] == "BIGINT" for row in rows))
            self.assertTrue(
                all(row["validation"] == "sampled-nonnull-exact-bigint-roundtrip" for row in rows)
            )

    def test_job_unknown_double_column_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "columns.csv"
            constraints = root / "constraints.csv"
            metadata.write_text(
                "table_name,column_name,data_type,is_nullable,ordinal_position\n"
                "x,new_measure,DOUBLE,YES,1\n",
                encoding="utf-8",
            )
            constraints.write_text(
                "table_name,constraint_index,constraint_type,column_name\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "python3", str(SCHEMA_TOOL),
                    "--metadata", str(metadata),
                    "--constraints", str(constraints),
                    "--schema", "pgplan_job",
                    "--family", "job",
                    "--table", "x",
                    "--provenance", "unit test",
                    "--out", str(root / "schema.sql"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("uses DOUBLE without a reviewed integral override", result.stderr)


class SampledLoaderTest(unittest.TestCase):
    @staticmethod
    def _write_executable(path: Path, body: str) -> None:
        path.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n" + textwrap.dedent(body),
            encoding="utf-8",
        )
        path.chmod(0o755)

    def test_graph_loader_uses_isolated_schema_and_verifies_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_duckdb = root / "duckdb"
            fake_psql = root / "psql"
            db = root / "graph.db"
            db.touch()
            psql_log = root / "psql.log"
            ddl_log = root / "ddl.sql"
            manifest = root / "manifest.tsv"

            self._write_executable(
                fake_duckdb,
                r"""
                sql=''
                for arg in "$@"; do sql="$arg"; done
                if [[ "$sql" == *information_schema.columns* ]]; then
                    python3 - "$sql" <<'PY'
import csv, re, sys
targets = re.findall(r"TO '([^']+)'", sys.argv[1])
assert len(targets) == 2, targets
with open(targets[0], "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["table_name", "column_name", "data_type", "is_nullable", "ordinal_position"])
    for i in range(1, 11):
        writer.writerow([f"R{i}", "src", "BIGINT", "YES", 1])
        writer.writerow([f"R{i}", "dst", "BIGINT", "YES", 2])
with open(targets[1], "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerow(["table_name", "constraint_index", "constraint_type", "column_name"])
PY
                elif [[ "$sql" == *"COPY ("* ]]; then
                    target="$(printf '%s' "$sql" | sed -n "s/.*TO '\([^']*\.csv\)'.*/\1/p")"
                    printf '1,2\n' > "$target"
                elif [[ "$sql" == *"SELECT count(*)"* ]]; then
                    printf '1\n'
                else
                    echo "unexpected fake DuckDB call: $*" >&2
                    exit 70
                fi
                """,
            )
            self._write_executable(
                fake_psql,
                r"""
                printf '%s\n' "$*" >> "$FAKE_PSQL_LOG"
                case "$*" in
                    *server_version_num*) printf '160002\n' ;;
                    *information_schema.schemata*) printf '0\n' ;;
                    *"--file="*)
                        file=''
                        for arg in "$@"; do
                            case "$arg" in
                                --file=*) file="$(printf '%s' "$arg" | cut -c 8-)" ;;
                            esac
                        done
                        cp "$file" "$FAKE_DDL_LOG"
                        ;;
                    *"\\copy "*) cat >/dev/null ;;
                    *"SELECT count(*) FROM"*) printf '1\n' ;;
                    *ANALYZE*) : ;;
                    *) echo "unexpected fake psql call: $*" >&2; exit 71 ;;
                esac
                """,
            )
            env = os.environ.copy()
            env.update(
                {
                    "OY_CONFIG_LOADED": "",
                    "DUCKDB_BIN": str(fake_duckdb),
                    "PSQL_BIN": str(fake_psql),
                    "PG_DSN": "host=fake dbname=plans",
                    "PGPLAN_SETUP": "source",
                    "FAKE_PSQL_LOG": str(psql_log),
                    "FAKE_DDL_LOG": str(ddl_log),
                }
            )
            result = subprocess.run(
                [
                    "bash", str(SAMPLED_LOADER),
                    "--family", "graph",
                    "--duckdb-db", str(db),
                    "--rows", "7",
                    "--manifest", str(manifest),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            ddl = ddl_log.read_text(encoding="utf-8")
            self.assertIn('CREATE SCHEMA IF NOT EXISTS "pgplan_graph";', ddl)
            self.assertIn('"r10"', ddl)
            self.assertIn('ANALYZE "pgplan_graph"."r1"', psql_log.read_text())
            self.assertIn('"plan_data":"graph-duckdb-sample-7"', result.stdout)
            with manifest.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source, delimiter="\t"))
            self.assertEqual(len(rows), 10)
            self.assertTrue(all(row["loaded_rows"] == "1" for row in rows))

    def _run_fake_job_loader(
        self, root: Path, invalid_column: str = ""
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
        fake_duckdb = root / "duckdb"
        fake_psql = root / "psql"
        db = root / "job.db"
        db.touch()
        duckdb_log = root / "duckdb.log"
        ddl_log = root / "ddl.sql"
        manifest = root / "manifest.tsv"

        self._write_executable(
            fake_duckdb,
            r"""
            sql=''
            for arg in "$@"; do sql="$arg"; done
            printf '%s\n-- call --\n' "$sql" >> "$FAKE_DUCKDB_LOG"
            if [[ "$sql" == *information_schema.columns* ]]; then
                python3 - "$sql" <<'PY'
import csv, re, sys
targets = re.findall(r"TO '([^']+)'", sys.argv[1])
assert len(targets) == 2, targets
tables = [
    "aka_name", "aka_title", "cast_info", "char_name", "comp_cast_type",
    "company_name", "company_type", "complete_cast", "info_type", "keyword",
    "kind_type", "link_type", "movie_companies", "movie_info", "movie_info_idx",
    "movie_keyword", "movie_link", "name", "person_info", "role_type", "title",
]
doubles = {
    "aka_title": ["production_year", "episode_of_id", "season_nr", "episode_nr"],
    "cast_info": ["person_role_id", "nr_order"],
    "char_name": ["imdb_id"],
    "company_name": ["imdb_id"],
    "name": ["imdb_id"],
    "title": ["production_year", "imdb_id", "episode_of_id", "season_nr", "episode_nr"],
}
with open(targets[0], "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["table_name", "column_name", "data_type", "is_nullable", "ordinal_position"])
    for table in tables:
        writer.writerow([table, "id", "INTEGER", "NO", 1])
        for ordinal, column in enumerate(doubles.get(table, []), 2):
            writer.writerow([table, column, "DOUBLE", "YES", ordinal])
with open(targets[1], "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["table_name", "constraint_index", "constraint_type", "column_name"])
    for table in tables:
        writer.writerow([table, 0, "PRIMARY KEY", "id"])
PY
            elif [[ "$sql" == *TRY_CAST* ]]; then
                if [ -n "${FAKE_INVALID_COLUMN:-}" ] && [[ "$sql" == *"\"$FAKE_INVALID_COLUMN\""* ]]; then
                    printf '1\n'
                else
                    printf '0\n'
                fi
            elif [[ "$sql" == *"COPY ("* ]]; then
                target="$(printf '%s' "$sql" | sed -n "s/.*TO '\([^']*\.csv\)'.*/\1/p")"
                printf '1\n' > "$target"
            elif [[ "$sql" == *"SELECT count(*)"* ]]; then
                printf '1\n'
            else
                echo "unexpected fake DuckDB call: $*" >&2
                exit 70
            fi
            """,
        )
        self._write_executable(
            fake_psql,
            r"""
            case "$*" in
                *server_version_num*) printf '160002\n' ;;
                *information_schema.schemata*) printf '0\n' ;;
                *"--file="*)
                    file=''
                    for arg in "$@"; do
                        case "$arg" in
                            --file=*) file="$(printf '%s' "$arg" | cut -c 8-)" ;;
                        esac
                    done
                    cp "$file" "$FAKE_DDL_LOG"
                    ;;
                *"\\copy "*) cat >/dev/null ;;
                *"SELECT count(*) FROM"*) printf '1\n' ;;
                *ANALYZE*) : ;;
                *) echo "unexpected fake psql call: $*" >&2; exit 71 ;;
            esac
            """,
        )
        env = os.environ.copy()
        env.update(
            {
                "OY_CONFIG_LOADED": "",
                "DUCKDB_BIN": str(fake_duckdb),
                "PSQL_BIN": str(fake_psql),
                "PG_DSN": "host=fake dbname=plans",
                "PGPLAN_SETUP": "source",
                "FAKE_DUCKDB_LOG": str(duckdb_log),
                "FAKE_DDL_LOG": str(ddl_log),
                "FAKE_INVALID_COLUMN": invalid_column,
            }
        )
        result = subprocess.run(
            [
                "bash", str(SAMPLED_LOADER),
                "--family", "job",
                "--duckdb-db", str(db),
                "--rows", "7",
                "--manifest", str(manifest),
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return result, duckdb_log, ddl_log, manifest

    def test_job_loader_validates_and_exports_all_reviewed_integral_doubles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result, duckdb_log, ddl_log, manifest = self._run_fake_job_loader(Path(temporary))
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = duckdb_log.read_text(encoding="utf-8")
            self.assertIn('TRY_CAST("production_year" AS BIGINT)', calls)
            self.assertIn('CAST("production_year" AS BIGINT) AS "production_year"', calls)
            self.assertIn('"production_year" BIGINT', ddl_log.read_text(encoding="utf-8"))
            self.assertIn('"validated_integral_coercions":14', result.stdout)
            with manifest.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source, delimiter="\t"))
            title = next(row for row in rows if row["table"] == "title")
            self.assertIn("production_year:DOUBLE->BIGINT", title["validated_integral_coercions"])

    def test_job_loader_rejects_fractional_sample_before_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result, _duckdb_log, _ddl_log, _manifest = self._run_fake_job_loader(
                Path(temporary), invalid_column="production_year"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("do not round-trip exactly as BIGINT", result.stderr)


class CorpusRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.auto_test = self.root / "auto_test"
        self.tools = self.auto_test / "postgres_replay"
        self.corpus = self.auto_test / "outerjoin_query"
        self.tools.mkdir(parents=True)
        for family in ("graph", "tpch", "tpcds", "job"):
            (self.corpus / family).mkdir(parents=True)
        shutil.copy2(CORPUS_RUNNER, self.tools / "corpus_experiment.sh")
        (self.tools / "corpus_experiment.sh").chmod(0o755)

        self.log = self.root / "calls.log"
        self.duckdb = self.root / "duckdb"
        self._write_executable(self.duckdb, "exit 0\n")
        self.databases = {}
        for family in ("graph", "tpch", "tpcds", "job"):
            path = self.root / f"{family}.db"
            path.touch()
            self.databases[family] = path
        (self.auto_test / "configs.sh").write_text(
            textwrap.dedent(
                f"""
                export DUCKDB_BIN="{self.duckdb}"
                export GRAPH_DB="{self.databases['graph']}"
                export TPCH_DB="{self.databases['tpch']}"
                export TPCDS_DB="{self.databases['tpcds']}"
                export JOB_DB="{self.databases['job']}"
                export OY_CORPUS="{self.corpus}"
                export PG_DSN='host=fake dbname=plans'
                export PGPLAN_SETUP=source
                export PGPLAN_VERSION_NUM=160002
                export PGPLAN_RUNS=1
                export PGPLAN_THREADS=2
                export PGPLAN_TIMEOUT_SECS=0
                export OY_TMPDIR="{self.root / 'tmp'}"
                """
            ).lstrip(),
            encoding="utf-8",
        )
        self._write_executable(
            self.tools / "setup_pg.sh",
            'printf "setup\\n" >> "$FAKE_CALL_LOG"\n',
        )
        self._write_executable(
            self.tools / "prepare_sampled_pg.sh",
            r"""
            printf 'prepare %s\n' "$*" >> "$FAKE_CALL_LOG"
            manifest=''
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    --manifest) manifest="$2"; shift 2 ;;
                    *) shift ;;
                esac
            done
            if [ -n "$manifest" ]; then
                mkdir -p "$(dirname "$manifest")"
                printf 'ok\n' > "$manifest"
            fi
            """,
        )
        self._write_executable(
            self.tools / "make_plan.sh",
            r"""
            printf 'capture %s\n' "$*" >> "$FAKE_CALL_LOG"
            out=''
            query=''
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    --out) out="$2"; shift 2 ;;
                    --query) query="$2"; shift 2 ;;
                    *) shift ;;
                esac
            done
            case "$query" in
                *bad.sql) echo 'intentional capture failure' >&2; exit 9 ;;
            esac
            printf '{"tree":{}}\n' > "$out"
            """,
        )
        self._write_executable(
            self.tools / "experiment.sh",
            r"""
            printf 'experiment %s\n' "$*" >> "$FAKE_CALL_LOG"
            out=''
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    --out) out="$2"; shift 2 ;;
                    *) shift ;;
                esac
            done
            mkdir -p "$out"
            """,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write_executable(path: Path, body: str) -> None:
        path.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n" + textwrap.dedent(body),
            encoding="utf-8",
        )
        path.chmod(0o755)

    def run_runner(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({"OY_CONFIG_LOADED": "", "FAKE_CALL_LOG": str(self.log)})
        return subprocess.run(
            ["bash", str(self.tools / "corpus_experiment.sh"), *arguments],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_only_pattern_and_global_limit_drive_capture_options(self) -> None:
        (self.corpus / "graph" / "a_keep.sql").write_text("SELECT 1;\n", encoding="utf-8")
        (self.corpus / "graph" / "b_skip.sql").write_text("SELECT 2;\n", encoding="utf-8")
        (self.corpus / "tpch" / "c_keep.sql").write_text("SELECT 3;\n", encoding="utf-8")
        out = self.root / "results"
        result = self.run_runner(
            "--only", "all",
            "--pattern", "*_keep",
            "--limit", "2",
            "--rows", "11",
            "--out", str(out),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(
            [row["query"] for row in status],
            ["graph/a_keep.sql", "tpch/c_keep.sql"],
        )
        self.assertTrue(all(row["status"] == "PASS" for row in status))
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("prepare "), 1)
        self.assertIn("--family graph", calls)
        self.assertIn("--rows 11", calls)
        self.assertIn("--pg-schema pgplan_graph", calls)
        self.assertIn("--plan-data graph-duckdb-sample-11", calls)
        self.assertIn("--pg-schema public", calls)
        self.assertIn("--plan-data tpch-sf0.01", calls)

    def test_capture_failure_is_recorded_and_later_query_continues(self) -> None:
        (self.corpus / "graph" / "a_bad.sql").write_text("SELECT 1;\n", encoding="utf-8")
        (self.corpus / "graph" / "b_good.sql").write_text("SELECT 2;\n", encoding="utf-8")
        out = self.root / "failed-results"
        result = self.run_runner("--only", "graph", "--runs", "1", "--out", str(out))
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in status], ["FAIL", "PASS"])
        self.assertEqual(status[0]["phase"], "capture")
        self.assertIn("intentional capture failure", status[0]["detail"])
        self.assertEqual(self.log.read_text(encoding="utf-8").count("experiment "), 1)


if __name__ == "__main__":
    unittest.main()
