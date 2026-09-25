#!/usr/bin/env python3
"""Focused tests for sampled family loading and corpus PGPlan orchestration."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_TOOL = SCRIPT_DIR / "schema_from_duckdb.py"
SAMPLED_LOADER = SCRIPT_DIR / "prepare_sampled_pg.sh"
CORPUS_RUNNER = SCRIPT_DIR / "corpus_experiment.sh"
EXPERIMENT = SCRIPT_DIR / "experiment.sh"
NORMALIZER = SCRIPT_DIR / "normalize_plan.py"


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
                elif [[ "$sql" == *"SELECT count(*) FROM"*rowid* ]]; then
                    printf '1\n'
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
            elif [[ "$sql" == *"SELECT count(*) FROM"*rowid* ]]; then
                printf '1\n'
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
            self.assertIn("WHERE rowid >= 0 AND rowid < 7", calls)
            self.assertNotIn("ORDER BY rowid LIMIT", calls)
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
        self.corpus = self.auto_test / "outerjoin_benchmark" / "benchmark"
        self.tools.mkdir(parents=True)
        for family in ("graph", "tpch", "tpcds", "job"):
            (self.corpus / family).mkdir(parents=True)
        shutil.copy2(CORPUS_RUNNER, self.tools / "corpus_experiment.sh")
        (self.tools / "corpus_experiment.sh").chmod(0o755)
        shutil.copy2(NORMALIZER, self.tools / "normalize_plan.py")
        shutil.copy2(SCHEMA_TOOL, self.tools / "schema_from_duckdb.py")
        shutil.copy2(SCRIPT_DIR / "tpch_schema.sql", self.tools / "tpch_schema.sql")

        self.log = self.root / "calls.log"
        self.tpch_content = self.root / "fake-tpch-sf001-content.txt"
        self.tpch_content.write_text("canonical sf0.01 content\n", encoding="utf-8")
        self.duckdb = self.root / "duckdb"
        self._write_executable(
            self.duckdb,
            r"""
            database="$1"
            shift
            sql=''
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    -c) sql="$2"; shift 2 ;;
                    *) shift ;;
                esac
            done
            case "$database:$sql" in
                *tpch_sf001.duckdb:*"SELECT * FROM"*)
                    cat "$FAKE_TPCH_CONTENT_FILE"
                    exit 0
                    ;;
            esac
            case "$sql" in
                *"SELECT count(*) FROM"*rowid*)
                    if [ -s "$database" ]; then printf '1\n'; else printf '0\n'; fi
                    ;;
                *information_schema.columns*)
                    printf 'fixed schema metadata\n'
                    ;;
                *duckdb_constraints*)
                    printf 'fixed constraint metadata\n'
                    ;;
                *"WHERE rowid >= 0 AND rowid <"*)
                    # Model a one-row bounded prefix. Additional file lines are
                    # outside the sample and must not affect its identity.
                    sed -n '1p' "$database"
                    ;;
                *)
                    :
                    ;;
            esac
            """,
        )
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
                export PGPLAN_PLAN_CACHE="{self.root / 'plan-cache'}"
                export PGPLAN_COMPARISON_MODE=both
                export PGPLAN_CAPTURE_TIMEOUT_SECS=60
                export PGPLAN_TIMEOUT_SECS=0
                export OY_TMPDIR="{self.root / 'tmp'}"
                export FAKE_TPCH_CONTENT_FILE="{self.tpch_content}"
                """
            ).lstrip(),
            encoding="utf-8",
        )
        self._write_executable(
            self.tools / "setup_pg.sh",
            r"""
            printf 'setup\n' >> "$FAKE_CALL_LOG"
            if [ "${FAKE_SETUP_FAIL:-0}" = "1" ]; then
                echo 'intentional PostgreSQL setup failure' >&2
                exit 17
            fi
            """,
        )
        self._write_executable(
            self.tools / "prepare_sampled_pg.sh",
            r"""
            printf 'prepare %s\n' "$*" >> "$FAKE_CALL_LOG"
            manifest=''
            family=''
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    --family) family="$2"; shift 2 ;;
                    --manifest) manifest="$2"; shift 2 ;;
                    *) shift ;;
                esac
            done
            if [ "${FAKE_PREPARE_FAIL_FAMILY:-}" = "$family" ]; then
                echo "intentional $family sampled-data preparation failure" >&2
                exit 19
            fi
            if [ -n "$manifest" ]; then
                mkdir -p "$(dirname "$manifest")"
                printf 'ok\n' > "$manifest"
            fi
            """,
        )
        self._write_executable(
            self.tools / "prepare_tpch_pg.sh",
            r"""
            printf 'prepare-tpch %s\n' "$*" >> "$FAKE_CALL_LOG"
            if [ "${FAKE_PREPARE_FAIL_FAMILY:-}" = "tpch" ]; then
                echo 'intentional tpch preparation failure' >&2
                exit 19
            fi
            """,
        )
        self._write_executable(
            self.tools / "prepare_correctness_db.sh",
            r"""
            printf 'correctness %s\n' "$*" >> "$FAKE_CALL_LOG"
            out=''
            manifest=''
            family=''
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    --family) family="$2"; shift 2 ;;
                    --out) out="$2"; shift 2 ;;
                    --manifest) manifest="$2"; shift 2 ;;
                    *) shift ;;
                esac
            done
            if [ "${FAKE_CORRECTNESS_FAIL_FAMILY:-}" = "$family" ]; then
                echo "intentional $family correctness preparation failure" >&2
                exit 7
            fi
            mkdir -p "$(dirname "$out")" "$(dirname "$manifest")"
            : > "$out"
            printf 'ok\n' > "$manifest"
            """,
        )
        self._write_executable(
            self.tools / "make_plan.sh",
            r"""
            printf 'capture %s\n' "$*" >> "$FAKE_CALL_LOG"
            out=''
            query=''
            pg_schema='public'
            plan_data='tpch-sf0.01'
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    --out) out="$2"; shift 2 ;;
                    --query) query="$2"; shift 2 ;;
                    --pg-schema) pg_schema="$2"; shift 2 ;;
                    --plan-data) plan_data="$2"; shift 2 ;;
                    *) shift ;;
                esac
            done
            case "$query" in
                *capture_timeout.sql)
                    echo '[PGPLAN] SKIP capture_timeout seconds=13' >&2
                    exit 124
                    ;;
                *bad.sql) echo 'intentional capture failure' >&2; exit 9 ;;
            esac
            case "$query" in
                *sample_race.sql)
                    printf 'changed during capture\n' > "$GRAPH_DB"
                    ;;
            esac
            tool_dir="$(cd "$(dirname "$0")" && pwd -P)"
            "${PYTHON_BIN:-python3}" -c '
import hashlib
import json
import sys
sys.path.insert(0, sys.argv[1])
from normalize_plan import FORMAT, QUERY_CANONICALIZATION, canonicalize_query
with open(sys.argv[2], "rb") as source:
    query_sha = hashlib.sha256(canonicalize_query(source.read())).hexdigest()
artifact = {
    "format": FORMAT,
    "query_sha256": query_sha,
    "query_sha256_canonicalization": QUERY_CANONICALIZATION,
    "postgres": {
        "version_num": 160002,
        "settings": ({"max_parallel_workers_per_gather": "0"}
                     if sys.argv[4] == "public" else
                     {"max_parallel_workers_per_gather": "0",
                      "search_path": "{}, pg_catalog".format(sys.argv[4])}),
        "plan_schema": sys.argv[4],
        "plan_data": sys.argv[5],
    },
    "tree": {
        "op": "scan", "schema": "public", "relation": "r1",
        "alias": "r1", "occurrence": 0,
    },
}
with open(sys.argv[3], "w", encoding="utf-8") as target:
    json.dump(artifact, target)
    target.write("\n")
' "$tool_dir" "$query" "$out" "$pg_schema" "$plan_data"
            """,
        )
        self._write_executable(
            self.tools / "experiment.sh",
            r"""
            printf 'experiment %s\n' "$*" >> "$FAKE_CALL_LOG"
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
                *execute_timeout.sql)
                    echo '[PGPLAN] TIMEOUT phase=correctness config=native limit_seconds=5' >&2
                    exit 124
                    ;;
            esac
            mkdir -p "$out/provenance"
            printf 'description=fake experiment\n' > "$out/provenance/manifest.txt"
            """,
        )
        self._write_executable(
            self.tools / "summarize_corpus.sh",
            r"""
            printf 'summarize %s\n' "$*" >> "$FAKE_CALL_LOG"
            out=''
            print_row=''
            total=''
            while [ "$#" -gt 0 ]; do
                case "$1" in
                    --result-dir) out="$2"; shift 2 ;;
                    --print-row) print_row="$2"; shift 2 ;;
                    --total) total="$2"; shift 2 ;;
                    *) shift ;;
                esac
            done
            print_status_row() {
                row="$(awk -F '\t' -v wanted="$print_row" 'NR == wanted + 1 {print; exit}' "$out/status.tsv")"
                [ -n "$row" ] || {
                    echo "missing status row $print_row" >&2
                    return 2
                }
                IFS="$(printf '\t')" read -r family query status phase detail plan result_dir <<EOF
$row
EOF
                label="$(basename "$query" .sql)"
                case "$status" in
                    PASS) correct=TRUE ;;
                    FAIL) correct=FALSE ;;
                    *) correct=NA ;;
                esac
                printf '%s\n' '===================================================================================================='
                printf '[ %d/%d] %s status=%s correct=%s\n' \
                    "$print_row" "$total" "$label" "$status" "$correct"
                printf 'details: family=%s sql=%s status=%s phase=%s detail=%s\n' \
                    "$family" "$query" "$status" "$phase" "$detail"
            }
            if [ -n "$print_row" ]; then
                if [ "${FAKE_SUMMARIZE_ROW_FAIL:-0}" = "1" ]; then
                    echo 'intentional live row formatter failure' >&2
                    exit 14
                fi
                print_status_row
                exit 0
            fi
            if [ "${FAKE_SUMMARIZE_FAIL:-0}" = "1" ]; then
                echo 'intentional aggregate report failure' >&2
                exit 13
            fi
            cp "$out/status.tsv" "$out/comparison.tsv"
            tr '\t' ',' < "$out/status.tsv" > "$out/comparison.csv"
            awk -F '\t' 'NR == 1 || $3 != "PASS"' "$out/status.tsv" > "$out/failures.tsv"
            {
                printf 'status\tcount\n'
                for status in PASS SKIP FAIL; do
                    count="$(awk -F '\t' -v wanted="$status" 'NR > 1 && $3 == wanted {count++} END {print count + 0}' "$out/status.tsv")"
                    printf '%s\t%s\n' "$status" "$count"
                done
            } > "$out/summary.tsv"
            : > "$out/comparison.log"
            row_count="$(awk 'END {print NR - 1}' "$out/status.tsv")"
            for print_row in $(seq 1 "$row_count"); do
                total="$row_count"
                print_status_row >> "$out/comparison.log"
            done
            printf '[comparison] fake report complete\n'
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

    def make_prior_run(
        self, prior: Path, family: str, label: str, with_plan: bool = True
    ) -> Path:
        run = prior / "runs" / family / label
        (run / "correctness").mkdir(parents=True, exist_ok=True)
        (run / "correctness" / "receipt.txt").write_text(
            "sealed fake target receipt\n", encoding="utf-8"
        )
        if with_plan:
            artifact = prior / "artifacts" / family / f"{label}.pg.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text('{"tree":{"source":"prior"}}\n', encoding="utf-8")
        return run

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
        self.assertEqual(result.stdout.count("plan sample fingerprint graph:"), 1)
        self.assertEqual(result.stdout.count("plan sample fingerprint tpch:"), 1)
        self.assertTrue(all(row["status"] == "PASS" for row in status))
        self.assertIn("[comparison] query 1/2: graph/a_keep.sql", result.stdout)
        self.assertIn("[comparison] query 2/2: tpch/c_keep.sql", result.stdout)
        self.assertIn("[pgplan] capture graph/a_keep.sql", result.stdout)
        self.assertIn("[comparison] execute graph/a_keep.sql", result.stdout)
        self.assertIn("[comparison] PASS graph/a_keep.sql", result.stdout)
        self.assertIn("[ 1/2] a_keep status=PASS correct=TRUE", result.stdout)
        self.assertIn("[ 2/2] c_keep status=PASS correct=TRUE", result.stdout)
        self.assertIn(
            "details: family=graph sql=graph/a_keep.sql status=PASS phase=complete",
            result.stdout,
        )
        self.assertIn(
            "[comparison] complete: selected=2 completed=2 skip=0 fail=0",
            result.stdout,
        )
        self.assertIn(
            "comparison_tsv={}/comparison.tsv".format(out.resolve()),
            result.stdout,
        )
        self.assertIn("----------------------------------------", result.stdout)
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("prepare "), 1)
        self.assertEqual(calls.count("correctness "), 0)
        self.assertIn("--family graph", calls)
        self.assertIn("--rows 11", calls)
        self.assertNotIn("--rows 500", calls)
        self.assertIn("--correctness-db", calls)
        self.assertIn(
            "--correctness-db {}".format(self.databases["graph"]),
            calls,
        )
        self.assertIn(
            "--correctness-db {}".format(self.databases["tpch"]),
            calls,
        )
        self.assertIn("--pg-schema pgplan_graph", calls)
        self.assertIn("--plan-data graph-duckdb-sample-11", calls)
        self.assertIn("--pg-schema public", calls)
        self.assertIn("--plan-data tpch-sf0.01", calls)
        summarize_calls = [line for line in calls.splitlines() if line.startswith("summarize ")]
        live_calls = [line for line in summarize_calls if "--print-row" in line]
        final_calls = [line for line in summarize_calls if "--print-row" not in line]
        self.assertEqual(len(live_calls), 2)
        self.assertEqual(len(final_calls), 1)
        self.assertIn("--print-row 1 --total 2", live_calls[0])
        self.assertIn("--print-row 2 --total 2", live_calls[1])
        self.assertIn("--result-dir {}".format(out.resolve()), calls)
        reports = (
            "comparison.tsv", "comparison.csv", "comparison.log",
            "summary.tsv", "failures.tsv",
        )
        for report in reports:
            self.assertTrue((out / report).is_file(), report)
        self.assertIn(
            "comparison_log={}/comparison.log".format(out.resolve()),
            result.stdout,
        )
        provenance = out / "runs" / "graph" / "a_keep" / "provenance"
        self.assertFalse((provenance / "correctness_db_manifest.tsv").exists())
        self.assertFalse((provenance / "correctness_db_fingerprints.tsv").exists())

    def test_fresh_capture_populates_cache_and_next_run_skips_postgres(self) -> None:
        query = self.corpus / "graph" / "cached.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first_out = self.root / "cache-first"
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(first_out)
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        cache_plan = self.root / "plan-cache" / "graph" / "cached.pg.json"
        self.assertTrue(cache_plan.is_file())
        self.assertEqual(
            cache_plan.read_bytes(),
            (first_out / "artifacts/graph/cached.pg.json").read_bytes(),
        )
        cache_table = (first_out / "plan_cache.tsv").read_text(encoding="utf-8")
        self.assertIn("graph\tgraph/cached.sql", cache_table)
        self.assertIn("\tPUBLISHED\t", cache_table)
        first_experiment = next(
            line for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.startswith("experiment ")
        )
        self.assertRegex(first_experiment, r"--execution-db-sha256 [0-9a-f]{64}")

        self.log.unlink()
        second_out = self.root / "cache-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(second_out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertNotIn("setup\n", calls)
        self.assertNotIn("prepare ", calls)
        self.assertNotIn("capture ", calls)
        self.assertEqual(calls.count("experiment "), 1)
        self.assertIn("all selected PGPlan artifacts hit", second.stdout)
        self.assertIn("[pgplan] cache hit graph/cached.sql", second.stdout)
        self.assertEqual(
            cache_plan.read_bytes(),
            (second_out / "artifacts/graph/cached.pg.json").read_bytes(),
        )
        self.assertIn(
            "\tHIT\t",
            (second_out / "plan_cache.tsv").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "validated query, artifact, and plan sample",
            (second_out / "plan_cache.tsv").read_text(encoding="utf-8"),
        )

    def test_plan_sample_change_invalidates_cache(self) -> None:
        query = self.corpus / "graph" / "sample_changed.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first_out = self.root / "sample-first"
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(first_out)
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        cache_plan = self.root / "plan-cache/graph/sample_changed.pg.json"
        cache_identity = Path(str(cache_plan) + ".plan_sample.sha256")
        first_identity = cache_identity.read_text(encoding="utf-8")

        # The fixture DuckDB emits database bytes as its sampled data.  A data
        # mutation must therefore make the otherwise valid artifact stale.
        self.databases["graph"].write_text("changed prefix row\n", encoding="utf-8")
        self.log.unlink()
        second_out = self.root / "sample-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(second_out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("setup\n", calls)
        self.assertIn("prepare ", calls)
        self.assertIn("capture ", calls)
        self.assertNotEqual(
            first_identity,
            cache_identity.read_text(encoding="utf-8"),
        )
        cache_table = (second_out / "plan_cache.tsv").read_text(encoding="utf-8")
        self.assertIn("\tMISS\t", cache_table)
        self.assertIn("\tPUBLISHED\t", cache_table)

    def test_sample_change_during_capture_fails_without_cache_publish(self) -> None:
        query = self.corpus / "graph" / "sample_race.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        self.databases["graph"].write_text("prefix before capture\n", encoding="utf-8")
        out = self.root / "sample-race"
        result = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(rows[0]["phase"], "plan_sample_changed")
        self.assertIn("sample changed during capture", rows[0]["detail"])
        cache_plan = self.root / "plan-cache/graph/sample_race.pg.json"
        self.assertFalse(cache_plan.exists())
        self.assertNotIn("experiment ", self.log.read_text(encoding="utf-8"))

    def test_rows_outside_bounded_prefix_do_not_invalidate_cache(self) -> None:
        query = self.corpus / "graph" / "outside_prefix.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        self.databases["graph"].write_text("prefix row\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(self.root / "prefix-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)

        with self.databases["graph"].open("a", encoding="utf-8") as target:
            target.write("row outside bounded prefix\n")
        self.log.unlink()
        out = self.root / "prefix-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertNotIn("setup\n", calls)
        self.assertNotIn("capture ", calls)
        self.assertIn("\tHIT\t", (out / "plan_cache.tsv").read_text())

    def test_schema_or_constraint_metadata_change_invalidates_cache(self) -> None:
        query = self.corpus / "graph" / "metadata_changed.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(self.root / "metadata-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)

        fake_source = self.duckdb.read_text(encoding="utf-8")
        self.duckdb.write_text(
            fake_source.replace(
                "fixed constraint metadata", "changed ordered constraint metadata"
            ),
            encoding="utf-8",
        )
        self.log.unlink()
        out = self.root / "metadata-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("setup\n", calls)
        self.assertIn("capture ", calls)
        self.assertIn("\tMISS\t", (out / "plan_cache.tsv").read_text())

    def test_loader_or_coercion_policy_change_invalidates_cache(self) -> None:
        query = self.corpus / "graph" / "policy_changed.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(self.root / "policy-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)

        with (self.tools / "schema_from_duckdb.py").open("a", encoding="utf-8") as target:
            target.write("\n# changed coercion policy identity\n")
        self.log.unlink()
        out = self.root / "policy-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("setup\n", calls)
        self.assertIn("capture ", calls)
        self.assertIn("\tMISS\t", (out / "plan_cache.tsv").read_text())

    def test_tpch_cache_uses_pinned_sf001_recipe_not_target_database_bytes(self) -> None:
        query = self.corpus / "tpch" / "pinned.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "tpch", "--runs", "1", "--out", str(self.root / "tpch-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        first_calls = self.log.read_text(encoding="utf-8")
        self.assertIn("prepare-tpch ", first_calls)
        self.assertIn("--duckdb-bin {} --force".format(self.duckdb), first_calls)

        self.databases["tpch"].write_text(
            "different target-scale database bytes\n", encoding="utf-8"
        )
        self.log.unlink()
        out = self.root / "tpch-second"
        second = self.run_runner(
            "--only", "tpch", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertNotIn("setup\n", calls)
        self.assertNotIn("capture ", calls)
        self.assertIn("\tHIT\t", (out / "plan_cache.tsv").read_text())

    def test_tpch_schema_recipe_change_invalidates_cache(self) -> None:
        query = self.corpus / "tpch" / "schema_pinned.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "tpch", "--runs", "1", "--out", str(self.root / "tpch-schema-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        with (self.tools / "tpch_schema.sql").open("a", encoding="utf-8") as target:
            target.write("\n-- changed canonical schema identity\n")

        self.log.unlink()
        out = self.root / "tpch-schema-second"
        second = self.run_runner(
            "--only", "tpch", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("setup\n", calls)
        self.assertIn("prepare-tpch ", calls)
        self.assertIn("capture ", calls)
        self.assertIn("\tMISS\t", (out / "plan_cache.tsv").read_text())

    def test_tpch_exact_content_change_invalidates_cache(self) -> None:
        query = self.corpus / "tpch" / "content_pinned.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "tpch", "--runs", "1", "--out", str(self.root / "tpch-content-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.tpch_content.write_text("different sf0.01 content\n", encoding="utf-8")

        self.log.unlink()
        out = self.root / "tpch-content-second"
        second = self.run_runner(
            "--only", "tpch", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("prepare-tpch ", calls)
        self.assertIn("capture ", calls)
        self.assertIn("\tMISS\t", (out / "plan_cache.tsv").read_text())

    def test_cache_without_plan_sample_identity_is_a_miss(self) -> None:
        query = self.corpus / "graph" / "legacy.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first_out = self.root / "legacy-first"
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(first_out)
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        cache_plan = self.root / "plan-cache/graph/legacy.pg.json"
        Path(str(cache_plan) + ".plan_sample.sha256").unlink()

        self.log.unlink()
        second_out = self.root / "legacy-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(second_out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("setup\n", calls)
        self.assertIn("capture ", calls)
        self.assertIn("\tMISS\t", (second_out / "plan_cache.tsv").read_text())

    def test_cache_identity_requires_loader_policy_files(self) -> None:
        query = self.corpus / "graph" / "helperless.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(self.root / "helper-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        for helper in ("setup_pg.sh", "prepare_sampled_pg.sh", "make_plan.sh"):
            (self.tools / helper).unlink()

        self.log.unlink()
        out = self.root / "helper-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(rows[0]["phase"], "plan_sample")
        calls = self.log.read_text(encoding="utf-8")
        self.assertNotIn("setup\n", calls)
        self.assertNotIn("capture ", calls)
        self.assertNotIn("experiment ", calls)

    def test_all_hits_do_not_require_setup_or_capture_helpers(self) -> None:
        query = self.corpus / "graph" / "safe_helperless.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(self.root / "safe-helper-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        (self.tools / "setup_pg.sh").unlink()
        (self.tools / "make_plan.sh").unlink()

        self.log.unlink()
        out = self.root / "safe-helper-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertNotIn("setup\n", calls)
        self.assertNotIn("capture ", calls)
        self.assertEqual(calls.count("experiment "), 1)

    def test_cache_settings_and_canonical_scan_schema_are_exact(self) -> None:
        query = self.corpus / "graph" / "strict_cache.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        initial_out = self.root / "strict-initial"
        initial = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(initial_out)
        )
        self.assertEqual(initial.returncode, 0, initial.stderr)
        cache_plan = self.root / "plan-cache/graph/strict_cache.pg.json"
        cache_identity = Path(str(cache_plan) + ".plan_sample.sha256")

        for ordinal, mutation in enumerate(("settings", "schema")):
            with self.subTest(mutation=mutation):
                artifact = json.loads(cache_plan.read_text(encoding="utf-8"))
                if mutation == "settings":
                    artifact["postgres"]["settings"].pop("search_path", None)
                else:
                    artifact["tree"]["schema"] = "main"
                cache_plan.write_text(
                    json.dumps(artifact) + "\n", encoding="utf-8"
                )
                artifact_sha = hashlib.sha256(cache_plan.read_bytes()).hexdigest()
                identity_lines = cache_identity.read_text(encoding="utf-8").splitlines()
                cache_identity.write_text(
                    "\n".join(
                        "artifact_sha256=" + artifact_sha
                        if line.startswith("artifact_sha256=") else line
                        for line in identity_lines
                    ) + "\n",
                    encoding="utf-8",
                )

                if self.log.exists():
                    self.log.unlink()
                out = self.root / "strict-{}".format(ordinal)
                result = self.run_runner(
                    "--only", "graph", "--runs", "1", "--out", str(out)
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self.log.read_text(encoding="utf-8")
                self.assertIn("setup\n", calls)
                self.assertIn("capture ", calls)
                self.assertIn("\tMISS\t", (out / "plan_cache.tsv").read_text())

    def test_mixed_statistics_epochs_recapture_selected_family(self) -> None:
        for label in ("a.sql", "b.sql"):
            (self.corpus / "graph" / label).write_text("SELECT 1;\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(self.root / "epoch-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        identities = [
            self.root / "plan-cache/graph/a.pg.json.plan_sample.sha256",
            self.root / "plan-cache/graph/b.pg.json.plan_sample.sha256",
        ]
        epochs = []
        for identity in identities:
            values = dict(
                line.split("=", 1)
                for line in identity.read_text(encoding="utf-8").splitlines()
            )
            epochs.append(values["stats_epoch"])
        self.assertEqual(epochs[0], epochs[1])

        lines = identities[1].read_text(encoding="utf-8").splitlines()
        replacement = "a" * 64 if epochs[0] != "a" * 64 else "b" * 64
        identities[1].write_text(
            "\n".join(
                "stats_epoch=" + replacement
                if line.startswith("stats_epoch=") else line
                for line in lines
            ) + "\n",
            encoding="utf-8",
        )
        self.log.unlink()
        out = self.root / "epoch-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("prepare "), 1)
        self.assertEqual(calls.count("capture "), 2)
        cache_table = (out / "plan_cache.tsv").read_text(encoding="utf-8")
        self.assertEqual(cache_table.count("\tRECACHE\t"), 2)

    def test_partial_family_cache_miss_recaptures_existing_hit(self) -> None:
        for label in ("a.sql", "b.sql"):
            (self.corpus / "graph" / label).write_text("SELECT 1;\n", encoding="utf-8")
        first = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(self.root / "partial-first")
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        cache_a = self.root / "plan-cache/graph/a.pg.json"
        cache_a.unlink()
        Path(str(cache_a) + ".plan_sample.sha256").unlink()

        self.log.unlink()
        out = self.root / "partial-second"
        second = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("prepare "), 1)
        self.assertEqual(calls.count("capture "), 2)
        self.assertIn("\tRECACHE\t", (out / "plan_cache.tsv").read_text())

    def test_other_family_cache_hit_executes_when_setup_fails_for_miss(self) -> None:
        hit_query = self.corpus / "tpcds" / "b_hit.sql"
        hit_query.write_text("SELECT 1;\n", encoding="utf-8")
        initial = self.run_runner(
            "--only", "tpcds", "--runs", "1", "--out", str(self.root / "mixed-initial")
        )
        self.assertEqual(initial.returncode, 0, initial.stderr)
        (self.corpus / "graph" / "a_miss.sql").write_text("SELECT 2;\n", encoding="utf-8")
        self.log.unlink()
        out = self.root / "mixed-setup-failure"
        env = os.environ.copy()
        env.update({
            "OY_CONFIG_LOADED": "",
            "FAKE_CALL_LOG": str(self.log),
            "FAKE_SETUP_FAIL": "1",
        })
        result = subprocess.run(
            [
                "bash", str(self.tools / "corpus_experiment.sh"),
                "--only", "all", "--runs", "1", "--out", str(out),
            ],
            cwd=self.root, env=env, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in rows], ["FAIL", "PASS"])
        self.assertEqual(rows[0]["phase"], "setup")
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("setup\n", calls)
        self.assertNotIn("prepare ", calls)
        self.assertNotIn("capture ", calls)
        self.assertEqual(calls.count("experiment "), 1)

    def test_other_family_cache_hit_executes_when_sampled_pg_preparation_fails(self) -> None:
        hit_query = self.corpus / "tpcds" / "b_hit.sql"
        hit_query.write_text("SELECT 1;\n", encoding="utf-8")
        initial = self.run_runner(
            "--only", "tpcds", "--runs", "1", "--out", str(self.root / "prep-initial")
        )
        self.assertEqual(initial.returncode, 0, initial.stderr)
        (self.corpus / "graph" / "a_miss.sql").write_text("SELECT 2;\n", encoding="utf-8")
        self.log.unlink()
        out = self.root / "mixed-prepare-failure"
        env = os.environ.copy()
        env.update({
            "OY_CONFIG_LOADED": "",
            "FAKE_CALL_LOG": str(self.log),
            "FAKE_PREPARE_FAIL_FAMILY": "graph",
        })
        result = subprocess.run(
            [
                "bash", str(self.tools / "corpus_experiment.sh"),
                "--only", "all", "--runs", "1", "--out", str(out),
            ],
            cwd=self.root, env=env, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in rows], ["FAIL", "PASS"])
        self.assertEqual(rows[0]["phase"], "prepare_plan_data")
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("setup\n", calls)
        self.assertEqual(calls.count("prepare "), 1)
        self.assertNotIn("capture ", calls)
        self.assertEqual(calls.count("experiment "), 1)

    def test_stale_cache_recaptures_and_comparison_aliases_reach_experiment(self) -> None:
        query = self.corpus / "graph" / "stale.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        initial_out = self.root / "stale-initial"
        initial = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(initial_out)
        )
        self.assertEqual(initial.returncode, 0, initial.stderr)

        query.write_text("SELECT 2;\n", encoding="utf-8")
        self.log.unlink()
        refreshed_out = self.root / "stale-refreshed"
        refreshed = self.run_runner(
            "--only", "graph", "--performance_only", "--runs", "1",
            "--out", str(refreshed_out),
        )
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("setup\n", calls)
        self.assertIn("capture ", calls)
        self.assertIn("--comparison-mode none", calls)
        self.assertNotIn("--reuse-correctness-from", calls)
        cache_table = (refreshed_out / "plan_cache.tsv").read_text(encoding="utf-8")
        self.assertIn("\tMISS\t", cache_table)
        self.assertIn("\tPUBLISHED\t", cache_table)
        run_config = (refreshed_out / "run_config.tsv").read_text(encoding="utf-8")
        self.assertIn("comparison_mode\tnone\n", run_config)

        alias_expectations = (
            ("--skip1", "pgplan-only"),
            ("--skip2", "none"),
            ("--performance-only", "none"),
            ("--performace_only", "none"),
        )
        for ordinal, (alias, expected) in enumerate(alias_expectations):
            with self.subTest(alias=alias):
                self.log.unlink()
                out = self.root / f"alias-{ordinal}"
                result = self.run_runner(
                    "--only", "graph", alias, "--runs", "1", "--out", str(out)
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(
                    f"--comparison-mode {expected}",
                    self.log.read_text(encoding="utf-8"),
                )
                self.assertIn(
                    f"comparison_mode\t{expected}\n",
                    (out / "run_config.tsv").read_text(encoding="utf-8"),
                )
                self.assertIn(
                    "target_db_graph_sha256\tNOT_COLLECTED\n",
                    (out / "run_config.tsv").read_text(encoding="utf-8"),
                )
                experiment_call = next(
                    line for line in self.log.read_text(encoding="utf-8").splitlines()
                    if line.startswith("experiment ")
                )
                self.assertNotIn("--execution-db-sha256", experiment_call)

    def test_cache_publish_failure_fails_query_and_continues_reporting(self) -> None:
        query = self.corpus / "graph" / "blocked.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        # A directory at the exact artifact destination makes the final atomic
        # replacement fail after capture and validation. The run must not call
        # the performance experiment while falsely claiming persistence.
        cache_plan = self.root / "plan-cache" / "graph" / "blocked.pg.json"
        cache_plan.mkdir(parents=True)
        out = self.root / "cache-publish-failure"

        result = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )

        self.assertNotEqual(result.returncode, 0)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "FAIL")
        self.assertEqual(rows[0]["phase"], "plan_cache")
        self.assertIn("could not publish persistent plan cache", result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("capture ", calls)
        self.assertNotIn("experiment ", calls)
        cache_table = (out / "plan_cache.tsv").read_text(encoding="utf-8")
        self.assertIn("\tPUBLISH_FAILED\t", cache_table)

    def test_bounded_correctness_is_explicit_and_retains_provenance(self) -> None:
        (self.corpus / "graph" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        out = self.root / "bounded-results"
        result = self.run_runner(
            "--only", "graph", "--correctness-mode", "bounded",
            "--runs", "1", "--out", str(out),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("correctness "), 1)
        self.assertIn("--rows 500", calls)
        self.assertIn(
            "--correctness-db {}/correctness_dbs/graph.duckdb".format(out.resolve()),
            calls,
        )
        provenance = out / "runs" / "graph" / "a" / "provenance"
        self.assertTrue((provenance / "correctness_db_manifest.tsv").is_file())
        self.assertTrue((provenance / "correctness_db_fingerprints.tsv").is_file())
        run_manifest = (provenance / "manifest.txt").read_text(encoding="utf-8")
        self.assertRegex(run_manifest, r"correctness_db_sha256=[0-9a-f]{64}\n")
        self.assertRegex(
            run_manifest,
            r"correctness_db_manifest_sha256=[0-9a-f]{64}\n",
        )

    def test_reuse_from_skips_postgres_and_reuses_plan_and_correctness(self) -> None:
        (self.corpus / "graph" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        prior = self.root / "prior corpus"
        prior_run = self.make_prior_run(prior, "graph", "a")
        out = self.root / "reuse-results"
        result = self.run_runner(
            "--only", "graph", "--reuse-from", str(prior),
            "--runs", "1", "--out", str(out),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertNotIn("setup\n", calls)
        self.assertNotIn("prepare ", calls)
        self.assertNotIn("capture ", calls)
        self.assertIn(f"--reuse-correctness-from {prior_run.resolve()}", calls)
        binary_sha = hashlib.sha256(self.duckdb.read_bytes()).hexdigest()
        database_sha = hashlib.sha256(self.databases["graph"].read_bytes()).hexdigest()
        self.assertIn(f"--duckdb-bin-sha256 {binary_sha}", calls)
        self.assertIn(f"--execution-db-sha256 {database_sha}", calls)
        copied_plan = out / "artifacts" / "graph" / "a.pg.json"
        self.assertEqual(
            copied_plan.read_text(encoding="utf-8"),
            '{"tree":{"source":"prior"}}\n',
        )
        self.assertIn("correctness mode=reuse", result.stdout)
        self.assertIn("PostgreSQL setup is not run", result.stdout)
        config = (out / "run_config.tsv").read_text(encoding="utf-8")
        self.assertIn("correctness_mode\treuse\n", config)
        self.assertIn(f"plan_reuse_from\t{prior.resolve()}\n", config)

    def test_granular_correctness_reuse_keeps_fresh_pgplan_capture(self) -> None:
        (self.corpus / "graph" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        prior = self.root / "prior-correctness"
        prior_run = self.make_prior_run(prior, "graph", "a", with_plan=False)
        out = self.root / "correctness-reuse-results"
        result = self.run_runner(
            "--only", "graph", "--correctness-mode", "reuse",
            "--correctness-from", str(prior), "--runs", "1", "--out", str(out),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("setup\n", calls)
        self.assertIn("prepare ", calls)
        self.assertIn("capture ", calls)
        self.assertIn(f"--reuse-correctness-from {prior_run.resolve()}", calls)

    def test_missing_reuse_plan_fails_query_and_later_query_continues(self) -> None:
        (self.corpus / "graph" / "a_missing.sql").write_text(
            "SELECT 1;\n", encoding="utf-8"
        )
        (self.corpus / "graph" / "b_good.sql").write_text(
            "SELECT 2;\n", encoding="utf-8"
        )
        prior = self.root / "prior-missing-plan"
        self.make_prior_run(prior, "graph", "a_missing", with_plan=False)
        self.make_prior_run(prior, "graph", "b_good", with_plan=True)
        out = self.root / "missing-plan-results"
        result = self.run_runner(
            "--only", "graph", "--reuse-from", str(prior),
            "--runs", "1", "--out", str(out),
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in status], ["FAIL", "PASS"])
        self.assertEqual(status[0]["phase"], "reuse_plan")
        self.assertIn("missing prior PGPlan artifact", status[0]["detail"])
        self.assertEqual(self.log.read_text(encoding="utf-8").count("experiment "), 1)

    def test_unsealed_reuse_receipt_fails_query_and_later_query_continues(self) -> None:
        (self.corpus / "graph" / "a_unsealed.sql").write_text(
            "SELECT 1;\n", encoding="utf-8"
        )
        (self.corpus / "graph" / "b_good.sql").write_text(
            "SELECT 2;\n", encoding="utf-8"
        )
        prior = self.root / "prior-unsealed-receipt"
        unsealed = self.make_prior_run(prior, "graph", "a_unsealed")
        (unsealed / "correctness" / "receipt.txt").unlink()
        good = self.make_prior_run(prior, "graph", "b_good")
        out = self.root / "unsealed-receipt-results"
        result = self.run_runner(
            "--only", "graph", "--reuse-from", str(prior),
            "--runs", "1", "--out", str(out),
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in status], ["FAIL", "PASS"])
        self.assertEqual(status[0]["phase"], "reuse_correctness")
        self.assertIn("missing sealed correctness receipt", status[0]["detail"])
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("experiment "), 1)
        self.assertIn(f"--reuse-correctness-from {good.resolve()}", calls)

    def test_reuse_plan_falls_back_to_prior_run_provenance_copy(self) -> None:
        (self.corpus / "graph" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        prior = self.root / "prior-fallback"
        prior_run = self.make_prior_run(prior, "graph", "a", with_plan=False)
        (prior_run / "provenance").mkdir()
        (prior_run / "provenance" / "postgres_plan.json").write_text(
            '{"tree":{"source":"run-provenance"}}\n', encoding="utf-8"
        )
        out = self.root / "fallback-results"
        result = self.run_runner(
            "--only", "graph", "--reuse-from", str(prior),
            "--runs", "1", "--out", str(out),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (out / "artifacts/graph/a.pg.json").read_text(encoding="utf-8"),
            '{"tree":{"source":"run-provenance"}}\n',
        )

    def test_reuse_plan_symlink_escape_fails_closed(self) -> None:
        (self.corpus / "graph" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        prior = self.root / "prior-plan-escape"
        self.make_prior_run(prior, "graph", "a", with_plan=False)
        artifact = prior / "artifacts/graph/a.pg.json"
        artifact.parent.mkdir(parents=True)
        outside = self.root / "outside-plan.json"
        outside.write_text('{"tree":{}}\n', encoding="utf-8")
        artifact.symlink_to(outside)
        out = self.root / "plan-escape-results"
        result = self.run_runner(
            "--only", "graph", "--reuse-from", str(prior),
            "--runs", "1", "--out", str(out),
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(status[0]["phase"], "reuse_plan")
        self.assertIn("escapes corpus", status[0]["detail"])
        self.assertNotIn("experiment ", self.log.read_text(encoding="utf-8"))

    def test_reuse_directory_symlink_escape_fails_closed(self) -> None:
        (self.corpus / "graph" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        prior = self.root / "prior-escape"
        (prior / "runs" / "graph").mkdir(parents=True)
        outside = self.root / "outside-run"
        (outside / "correctness").mkdir(parents=True)
        (outside / "correctness" / "receipt.txt").write_text("fake\n", encoding="utf-8")
        (prior / "runs" / "graph" / "a").symlink_to(outside, target_is_directory=True)
        out = self.root / "escape-results"
        result = self.run_runner(
            "--only", "graph", "--reuse-from", str(prior),
            "--runs", "1", "--out", str(out),
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(status[0]["phase"], "reuse_correctness")
        self.assertIn("escapes corpus", status[0]["detail"])
        self.assertNotIn("experiment ", self.log.read_text(encoding="utf-8"))

    def test_nonempty_target_wal_fails_family_without_experiment(self) -> None:
        (self.corpus / "graph" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        Path(str(self.databases["graph"]) + ".wal").write_text(
            "pending", encoding="utf-8"
        )
        out = self.root / "wal-results"
        result = self.run_runner(
            "--only", "graph", "--runs", "1", "--out", str(out)
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(status[0]["phase"], "prepare")
        self.assertIn("non-empty WAL", status[0]["detail"])
        self.assertNotIn("experiment ", self.log.read_text(encoding="utf-8"))

    def test_bounded_builder_failure_cannot_affect_target_mode(self) -> None:
        (self.corpus / "tpcds" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        out = self.root / "target-ignores-bounded-builder"
        env = os.environ.copy()
        env.update(
            {
                "OY_CONFIG_LOADED": "",
                "FAKE_CALL_LOG": str(self.log),
                "FAKE_CORRECTNESS_FAIL_FAMILY": "tpcds",
            }
        )
        result = subprocess.run(
            [
                "bash", str(self.tools / "corpus_experiment.sh"),
                "--only", "tpcds", "--runs", "1", "--out", str(out),
            ],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertNotIn("correctness ", calls)
        self.assertIn("--correctness-db {}".format(self.databases["tpcds"]), calls)

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
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("experiment "), 1)
        summarize_calls = [line for line in calls.splitlines() if line.startswith("summarize ")]
        self.assertEqual(
            len([line for line in summarize_calls if "--print-row" in line]),
            2,
        )
        self.assertEqual(
            len([line for line in summarize_calls if "--print-row" not in line]),
            1,
        )
        self.assertIn("[ 1/2] a_bad status=FAIL correct=FALSE", result.stdout)
        self.assertIn(
            "details: family=graph sql=graph/a_bad.sql status=FAIL phase=capture",
            result.stdout,
        )
        self.assertIn("[ 2/2] b_good status=PASS correct=TRUE", result.stdout)
        self.assertIn(
            "[comparison] complete: selected=2 completed=1 skip=0 fail=1",
            result.stdout,
        )
        reports = (
            "comparison.tsv", "comparison.csv", "comparison.log",
            "summary.tsv", "failures.tsv",
        )
        for report in reports:
            self.assertTrue((out / report).is_file(), report)

    def test_structural_report_failure_makes_a_passing_corpus_fail(self) -> None:
        (self.corpus / "graph" / "a_good.sql").write_text(
            "SELECT 1;\n", encoding="utf-8"
        )
        out = self.root / "report-failure-results"
        env = os.environ.copy()
        env.update(
            {
                "OY_CONFIG_LOADED": "",
                "FAKE_CALL_LOG": str(self.log),
                "FAKE_SUMMARIZE_FAIL": "1",
            }
        )
        result = subprocess.run(
            [
                "bash",
                str(self.tools / "corpus_experiment.sh"),
                "--only",
                "graph",
                "--runs",
                "1",
                "--out",
                str(out),
            ],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in status], ["PASS"])
        self.assertIn("comparison corpus report generation failed", result.stderr)
        self.assertIn(
            "[comparison] complete: selected=1 completed=1 skip=0 fail=0",
            result.stdout,
        )
        summarize_calls = [
            line for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.startswith("summarize ")
        ]
        self.assertEqual(
            len([line for line in summarize_calls if "--print-row" in line]),
            1,
        )
        self.assertEqual(
            len([line for line in summarize_calls if "--print-row" not in line]),
            1,
        )

    def test_live_formatter_failure_fails_closed_without_duplicate_status(self) -> None:
        (self.corpus / "graph" / "a_good.sql").write_text(
            "SELECT 1;\n", encoding="utf-8"
        )
        out = self.root / "live-report-failure-results"
        env = os.environ.copy()
        env.update(
            {
                "OY_CONFIG_LOADED": "",
                "FAKE_CALL_LOG": str(self.log),
                "FAKE_SUMMARIZE_ROW_FAIL": "1",
            }
        )
        result = subprocess.run(
            [
                "bash",
                str(self.tools / "corpus_experiment.sh"),
                "--only",
                "graph",
                "--runs",
                "1",
                "--out",
                str(out),
            ],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["status"], "PASS")
        self.assertIn("could not format comparison result row 1", result.stderr)
        summarize_calls = [
            line for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.startswith("summarize ")
        ]
        self.assertEqual(
            len([line for line in summarize_calls if "--print-row" in line]),
            1,
        )
        self.assertEqual(
            len([line for line in summarize_calls if "--print-row" not in line]),
            1,
        )
        self.assertTrue((out / "comparison.log").is_file())

    def test_setup_failure_renders_every_query_and_final_comparison_log(self) -> None:
        (self.corpus / "graph" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        (self.corpus / "graph" / "b.sql").write_text("SELECT 2;\n", encoding="utf-8")
        out = self.root / "setup-failure-results"
        env = os.environ.copy()
        env.update(
            {
                "OY_CONFIG_LOADED": "",
                "FAKE_CALL_LOG": str(self.log),
                "FAKE_SETUP_FAIL": "1",
            }
        )
        result = subprocess.run(
            [
                "bash",
                str(self.tools / "corpus_experiment.sh"),
                "--only",
                "graph",
                "--runs",
                "1",
                "--out",
                str(out),
            ],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in status], ["FAIL", "FAIL"])
        self.assertTrue(all(row["phase"] == "setup" for row in status))
        summarize_calls = [
            line for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.startswith("summarize ")
        ]
        self.assertEqual(len(summarize_calls), 3)
        self.assertEqual(
            len([line for line in summarize_calls if "--print-row" in line]), 2
        )
        comparison_log = (out / "comparison.log").read_text(encoding="utf-8")
        self.assertIn("[ 1/2] a status=FAIL", comparison_log)
        self.assertIn("[ 2/2] b status=FAIL", comparison_log)
        self.assertIn("[ 1/2] a status=FAIL", result.stdout)
        self.assertIn("[ 2/2] b status=FAIL", result.stdout)

    def test_capture_timeout_is_skipped_without_running_the_experiment(self) -> None:
        (self.corpus / "graph" / "a_capture_timeout.sql").write_text(
            "SELECT 1;\n", encoding="utf-8"
        )
        (self.corpus / "graph" / "b_good.sql").write_text(
            "SELECT 2;\n", encoding="utf-8"
        )
        out = self.root / "capture-timeout-results"
        result = self.run_runner(
            "--only", "graph", "--capture-timeout", "13", "--runs", "1",
            "--out", str(out),
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in status], ["SKIP", "PASS"])
        self.assertEqual(status[0]["phase"], "capture_timeout")
        self.assertIn("seconds=13", status[0]["detail"])
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("--capture-timeout 13", calls)
        self.assertEqual(calls.count("experiment "), 1)
        self.assertIn(
            "[ 1/2] a_capture_timeout status=SKIP correct=NA",
            result.stdout,
        )
        self.assertIn(
            "details: family=graph sql=graph/a_capture_timeout.sql "
            "status=SKIP phase=capture_timeout",
            result.stdout,
        )
        summarize_calls = [line for line in calls.splitlines() if line.startswith("summarize ")]
        self.assertEqual(
            len([line for line in summarize_calls if "--print-row" in line]),
            2,
        )
        self.assertEqual(
            len([line for line in summarize_calls if "--print-row" not in line]),
            1,
        )

    def test_execution_timeout_is_skipped_and_later_query_continues(self) -> None:
        (self.corpus / "graph" / "a_execute_timeout.sql").write_text(
            "SELECT 1;\n", encoding="utf-8"
        )
        (self.corpus / "graph" / "b_good.sql").write_text(
            "SELECT 2;\n", encoding="utf-8"
        )
        out = self.root / "execute-timeout-results"
        result = self.run_runner(
            "--only", "graph", "--timeout", "5", "--runs", "1",
            "--out", str(out),
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in status], ["SKIP", "PASS"])
        self.assertEqual(status[0]["phase"], "execute_timeout")
        self.assertIn("phase=correctness", status[0]["detail"])
        self.assertEqual(self.log.read_text(encoding="utf-8").count("experiment "), 2)

    def test_correctness_database_failure_fails_closed_for_the_family(self) -> None:
        (self.corpus / "graph" / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
        (self.corpus / "graph" / "b.sql").write_text("SELECT 2;\n", encoding="utf-8")
        out = self.root / "correctness-prepare-failure"
        env = os.environ.copy()
        env.update(
            {
                "OY_CONFIG_LOADED": "",
                "FAKE_CALL_LOG": str(self.log),
                "FAKE_CORRECTNESS_FAIL_FAMILY": "graph",
            }
        )
        result = subprocess.run(
            [
                "bash",
                str(self.tools / "corpus_experiment.sh"),
                "--only",
                "graph",
                "--correctness-mode",
                "bounded",
                "--runs",
                "1",
                "--out",
                str(out),
            ],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        with (out / "status.tsv").open(newline="", encoding="utf-8") as source:
            status = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual([row["status"] for row in status], ["FAIL", "FAIL"])
        self.assertTrue(all(row["phase"] == "prepare" for row in status))
        self.assertIn("correctness preparation failure", status[0]["detail"])
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("correctness "), 1)
        self.assertNotIn("capture ", calls)
        self.assertNotIn("experiment ", calls)


class ExperimentTimeoutTest(unittest.TestCase):
    def run_experiment_with_duck_exit(self, duck_exit: int, duck_stderr=""):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        duckdb = root / "duckdb"
        stderr_command = ""
        if duck_stderr:
            stderr_command = "printf '%s\\n' {} >&2\n".format(
                shlex.quote(duck_stderr)
            )
        duckdb.write_text(
            "#!/usr/bin/env bash\n{}exit {}\n".format(
                stderr_command, duck_exit
            ),
            encoding="utf-8",
        )
        duckdb.chmod(0o755)
        database = root / "execution.db"
        database.touch()
        query = root / "query.sql"
        query.write_text("SELECT 1;\n", encoding="utf-8")
        plan = root / "plan.json"
        plan.write_text(
            '{"postgres":{"plan_data":"tpch-sf0.01","plan_schema":"public"}}\n',
            encoding="utf-8",
        )
        out = root / "out"
        env = os.environ.copy()
        env.pop("PGPLAN_CORRECTNESS_DB", None)
        env.update(
            {
                "PYTHON_BIN": sys.executable,
                "PGPLAN_TIMEOUT_SECS": "1",
                "PGPLAN_TIMEOUT_GRACE": "0",
                "PGPLAN_TMPDIR": str(root / "tmp"),
            }
        )
        result = subprocess.run(
            [
                "bash", str(EXPERIMENT),
                "--duckdb-bin", str(duckdb),
                "--execution-db", str(database),
                "--query", str(query),
                "--plan", str(plan),
                "--runs", "1",
                "--threads", "1",
                "--out", str(out),
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return result, out

    def test_reserved_timeout_exit_has_stable_marker(self) -> None:
        result, out = self.run_experiment_with_duck_exit(124)
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertIn(
            "[PGPLAN] TIMEOUT phase=version config=metadata limit_seconds=1",
            result.stderr,
        )
        self.assertIn(
            "status=SKIP",
            (out / "provenance/manifest.txt").read_text(encoding="utf-8"),
        )

    def test_non_timeout_duck_failure_remains_failure(self) -> None:
        result, _out = self.run_experiment_with_duck_exit(9)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("[PGPLAN] TIMEOUT", result.stderr)

    def test_timeout_setting_error_is_not_misclassified_as_timeout(self) -> None:
        result, _out = self.run_experiment_with_duck_exit(
            9,
            "Catalog Error: unrecognized configuration parameter max_execution_time",
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("[PGPLAN] TIMEOUT", result.stderr)


class ExperimentPostprocessTimeoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.duckdb = self.root / "duckdb"
        self.duckdb.write_text(
            textwrap.dedent(
                r"""
                #!/usr/bin/env python3
                import os
                from pathlib import Path
                import re
                import sys

                sql = sys.stdin.read()
                def emit_pgplan():
                    print(
                        '[PGPLAN] {"event":"imported",'
                        '"query_sha256_verified":true,'
                        '"artifact_raw_signature":"J[inner](S:l,S:r)",'
                        '"imported_raw_signature":"J[inner](S:l,S:r)",'
                        '"implied_equality_count":1,'
                        '"expected_semantic_signature":"I(S:l,S:r)"}',
                        file=sys.stderr,
                    )
                    print(
                        '[PGPLAN] {"event":"verified",'
                        '"expected_semantic_signature":"I(S:l,S:r)",'
                        '"final_semantic_signature":"I(S:l,S:r)"}',
                        file=sys.stderr,
                    )
                if "pragma_version()" in sql:
                    call_kind = "version"
                elif "duckdb_settings()" in sql:
                    call_kind = "settings"
                elif "EXPLAIN " in sql:
                    call_kind = "explain"
                elif ".mode csv" in sql:
                    call_kind = "correctness"
                elif ".timer on" in sql:
                    call_kind = "timing"
                else:
                    call_kind = "unknown"
                call_log = os.environ.get("FAKE_DUCK_CALL_LOG")
                if call_log:
                    with open(call_log, "a", encoding="utf-8") as target:
                        target.write("{}\t{}\n".format(call_kind, sys.argv[-1]))

                trace = os.environ.get("DUCKDB_OYTRACE")
                if trace:
                    Path(trace).write_text(
                        "[OY_DECISION] selected_plan=DUCKDB{}\n".format(
                            os.environ.get("FAKE_OY_DECISION_EXTRA", "")
                        ),
                        encoding="utf-8",
                    )

                if "pragma_version()" in sql:
                    print("vtest")
                elif "duckdb_settings()" in sql:
                    if "SET disabled_optimizers TO ''" in sql:
                        print("disabled_optimizers,")
                    else:
                        print("disabled_optimizers,outer_yan")
                    pgplan = re.search(
                        r"SELECT 'pgplan' AS name, '([^']*)' AS value", sql
                    )
                    if pgplan:
                        print("pgplan,{},VARCHAR".format(pgplan.group(1)))
                elif "EXPLAIN " in sql:
                    if "SET VARIABLE pgplan = '" in sql:
                        emit_pgplan()
                    print("logical_plan")
                elif ".mode csv" in sql:
                    if "SET VARIABLE pgplan = '" in sql:
                        emit_pgplan()
                    if (
                        os.environ.get("FAKE_DUCK_MISMATCH_PGPLAN") == "1"
                        and "SET VARIABLE pgplan = '" in sql
                    ):
                        print("2")
                    else:
                        print("1")
                elif ".timer on" in sql:
                    if os.environ.get("FAKE_DUCK_TIMING_FAILURE") == "1":
                        raise SystemExit(9)
                    for _index in range(sql.count("SELECT 1\n;\n")):
                        print("Run Time (s): real 0.001 user 0.000 sys 0.000")
                """
            ).lstrip(),
            encoding="utf-8",
        )
        self.duckdb.chmod(0o755)
        self.database = self.root / "execution.db"
        self.database.touch()
        self.query = self.root / "query.sql"
        self.query.write_text("SELECT 1;\n", encoding="utf-8")
        self.plan = self.root / "plan.json"
        self.plan.write_text(
            '{"postgres":{"plan_data":"tpch-sf0.01","plan_schema":"public"}}\n',
            encoding="utf-8",
        )

    def write_tool(self, name: str, source: str) -> Path:
        path = self.tools / name
        path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
        path.chmod(0o755)
        return path

    def run_experiment(self, extra_args=(), out_name="out", **overrides: str):
        out = self.root / out_name
        env = os.environ.copy()
        for name in (
            "PGPLAN_CORRECTNESS_DB",
            "PGPLAN_COMPARISON_MODE",
            "PGPLAN_REUSE_CORRECTNESS_FROM",
            "PGPLAN_EXECUTION_DB_SHA256",
            "PGPLAN_DUCKDB_BIN_SHA256",
        ):
            env.pop(name, None)
        env.update(
            {
                "PATH": str(self.tools) + os.pathsep + env.get("PATH", ""),
                "PYTHON_BIN": sys.executable,
                "PGPLAN_TIMEOUT_SECS": "1",
                "PGPLAN_TIMEOUT_GRACE": "0",
                "PGPLAN_TMPDIR": str(self.root / "tmp"),
            }
        )
        env.update(overrides)
        command = [
            "bash",
            str(EXPERIMENT),
            "--duckdb-bin",
            str(self.duckdb),
            "--execution-db",
            str(self.database),
            "--query",
            str(self.query),
            "--plan",
            str(self.plan),
            "--runs",
            "1",
            "--threads",
            "16",
        ]
        command.extend(extra_args)
        command.extend(["--out", str(out)])
        result = subprocess.run(
            command,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return result, out

    @staticmethod
    def assert_postprocess_timeout(result, out: Path, phase: str, config: str):
        marker = (
            "[PGPLAN] TIMEOUT phase={} config={} limit_seconds=1".format(
                phase, config
            )
        )
        if result.returncode != 124:
            raise AssertionError(result.stderr)
        if marker not in result.stderr:
            raise AssertionError(result.stderr)
        manifest = (out / "provenance/manifest.txt").read_text(encoding="utf-8")
        if "status=SKIP" not in manifest:
            raise AssertionError(manifest)
        if "skip_reason=postprocess_timeout" not in manifest:
            raise AssertionError(manifest)

    def assert_database_routing(self, call_log: Path, correctness_db: Path) -> None:
        calls = [
            tuple(line.split("\t", 1))
            for line in call_log.read_text(encoding="utf-8").splitlines()
        ]
        kinds = [kind for kind, _database in calls]
        self.assertEqual(kinds.count("version"), 1)
        self.assertEqual(kinds.count("settings"), 3)
        self.assertEqual(kinds.count("explain"), 3)
        self.assertEqual(kinds.count("correctness"), 3)
        # One multi-thread batch for each of the three configurations.
        self.assertEqual(kinds.count("timing"), 3)
        self.assertNotIn("unknown", kinds)
        for kind, database in calls:
            expected = correctness_db if kind == "correctness" else self.database
            self.assertEqual(database, str(expected.resolve()), (kind, database))

    def test_correctness_database_environment_is_isolated_from_target_work(self) -> None:
        correctness_db = self.root / "correctness.db"
        correctness_db.touch()
        call_log = self.root / "database-calls.tsv"
        result, out = self.run_experiment(
            PGPLAN_CORRECTNESS_DB=str(correctness_db),
            FAKE_DUCK_CALL_LOG=str(call_log),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_database_routing(call_log, correctness_db)
        manifest = (out / "provenance/manifest.txt").read_text(encoding="utf-8")
        self.assertIn("execution_db={}\n".format(self.database.resolve()), manifest)
        self.assertIn("correctness_db={}\n".format(correctness_db.resolve()), manifest)

    def test_correctness_database_defaults_to_execution_database(self) -> None:
        call_log = self.root / "default-database-calls.tsv"
        result, out = self.run_experiment(FAKE_DUCK_CALL_LOG=str(call_log))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_database_routing(call_log, self.database)
        manifest = (out / "provenance/manifest.txt").read_text(encoding="utf-8")
        expected = str(self.database.resolve())
        self.assertIn("execution_db={}\n".format(expected), manifest)
        self.assertIn("correctness_db={}\n".format(expected), manifest)
        self.assertRegex(manifest, r"execution_db_sha256=[0-9a-f]{64}\n")
        self.assertIn("execution_db_sha256_source=computed\n", manifest)
        with (out / "timing/summary.tsv").open(
            newline="", encoding="utf-8"
        ) as source:
            timing_rows = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(
            [row["configuration"] for row in timing_rows],
            ["native", "pgplan", "outer_yan"],
        )
        self.assertTrue(all(row["threads"] == "16" for row in timing_rows))
        self.assertTrue(all(row["measured_runs"] == "1" for row in timing_rows))
        self.assertFalse(list((out / "timing").glob("t1_*")))

    def test_pgplan_only_runs_two_correctness_queries_but_all_timing_modes(self) -> None:
        call_log = self.root / "pgplan-only-calls.tsv"
        result, out = self.run_experiment(
            extra_args=("--comparison-mode", "pgplan-only"),
            FAKE_DUCK_CALL_LOG=str(call_log),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        kinds = [
            line.split("\t", 1)[0]
            for line in call_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(kinds.count("correctness"), 2)
        self.assertEqual(kinds.count("settings"), 3)
        self.assertEqual(kinds.count("explain"), 3)
        self.assertEqual(kinds.count("timing"), 3)
        with (out / "correctness/row_counts.tsv").open(
            newline="", encoding="utf-8"
        ) as source:
            rows = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(
            [row["configuration"] for row in rows], ["native", "pgplan"]
        )
        self.assertTrue((out / "correctness/pgplan.comparison.txt").is_file())
        self.assertFalse((out / "correctness/outer_yan.comparison.txt").exists())
        self.assertTrue((out / "traces/pgplan_correctness.trace").is_file())
        self.assertFalse(
            (out / "traces/outer_yan_correctness_decision.trace").exists()
        )
        self.assertFalse((out / "correctness/receipt.txt").exists())
        self.assertTrue((out / "correctness/unsealed.txt").is_file())
        self.assertTrue(
            (out / "correctness/status.txt")
            .read_text(encoding="utf-8")
            .startswith("PARTIAL:")
        )
        manifest = dict(
            line.split("=", 1)
            for line in (out / "provenance/manifest.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(manifest["comparison_mode"], "pgplan-only")
        self.assertEqual(manifest["correctness_origin"], "PARTIAL")
        self.assertEqual(manifest["correctness_status"], "PARTIAL")
        self.assertEqual(manifest["correctness_comparison_executed"], "1")
        self.assertEqual(manifest["correctness_comparison_set"], "pgplan-only")
        self.assertEqual(manifest["execution_db_sha256"], "NOT_COLLECTED")
        self.assertEqual(manifest["execution_db_sha256_source"], "not_collected")
        self.assertEqual(manifest["correctness_db_sha256"], "NOT_COLLECTED")

    def test_none_runs_no_correctness_but_all_explain_and_timing_modes(self) -> None:
        call_log = self.root / "none-calls.tsv"
        result, out = self.run_experiment(
            PGPLAN_COMPARISON_MODE="none", FAKE_DUCK_CALL_LOG=str(call_log)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        kinds = [
            line.split("\t", 1)[0]
            for line in call_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(kinds.count("correctness"), 0)
        self.assertEqual(kinds.count("settings"), 3)
        self.assertEqual(kinds.count("explain"), 3)
        self.assertEqual(kinds.count("timing"), 3)
        self.assertFalse((out / "correctness/row_counts.tsv").exists())
        self.assertFalse((out / "correctness/pgplan.comparison.txt").exists())
        self.assertFalse((out / "correctness/outer_yan.comparison.txt").exists())
        self.assertFalse((out / "correctness/receipt.txt").exists())
        self.assertTrue(
            (out / "correctness/status.txt")
            .read_text(encoding="utf-8")
            .startswith("NOT_RUN:")
        )
        manifest = dict(
            line.split("=", 1)
            for line in (out / "provenance/manifest.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(manifest["comparison_mode"], "none")
        self.assertEqual(manifest["correctness_origin"], "NOT_RUN")
        self.assertEqual(manifest["correctness_status"], "NOT_RUN")
        self.assertEqual(manifest["correctness_comparison_executed"], "0")
        self.assertEqual(manifest["correctness_comparison_set"], "none")
        self.assertEqual(manifest["execution_db_sha256"], "NOT_COLLECTED")
        self.assertEqual(manifest["execution_db_sha256_source"], "not_collected")
        self.assertEqual(manifest["correctness_db_sha256"], "NOT_RUN")

    def test_comparison_mode_cli_overrides_environment(self) -> None:
        call_log = self.root / "comparison-override-calls.tsv"
        result, _out = self.run_experiment(
            extra_args=("--comparison-mode", "pgplan-only"),
            PGPLAN_COMPARISON_MODE="none",
            FAKE_DUCK_CALL_LOG=str(call_log),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        kinds = [
            line.split("\t", 1)[0]
            for line in call_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(kinds.count("correctness"), 2)

    def test_invalid_comparison_mode_is_usage_error(self) -> None:
        result, _out = self.run_experiment(
            extra_args=("--comparison-mode", "sometimes"),
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("must be both, pgplan-only, or none", result.stderr)

    def test_fresh_target_correctness_emits_sealed_receipt_before_timing(self) -> None:
        result, out = self.run_experiment(FAKE_DUCK_TIMING_FAILURE="1")
        self.assertEqual(result.returncode, 1, result.stderr)
        receipt = out / "correctness/receipt.txt"
        self.assertTrue(receipt.is_file())
        receipt_values = dict(
            line.split("=", 1)
            for line in receipt.read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual(receipt_values["status"], "PASS")
        self.assertEqual(receipt_values["scope"], "target")
        self.assertEqual(receipt_values["comparison_mode"], "both")
        self.assertEqual(receipt_values["rows"], "1")
        self.assertRegex(receipt_values["multiset_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            receipt_values["pgplan_expected_semantic_signature"],
            receipt_values["pgplan_final_semantic_signature"],
        )
        manifest = dict(
            line.split("=", 1)
            for line in (out / "provenance/manifest.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(manifest["correctness_origin"], "FRESH")
        self.assertEqual(manifest["correctness_status"], "PASS")
        self.assertEqual(manifest["correctness_comparison_executed"], "1")
        self.assertEqual(manifest["correctness_comparison_set"], "both")
        self.assertEqual(manifest["comparison_mode"], "both")
        self.assertEqual(
            manifest["correctness_receipt_sha256"],
            hashlib.sha256(receipt.read_bytes()).hexdigest(),
        )
        for name in (
            "settings_native",
            "settings_pgplan",
            "settings_outer_yan",
            "plan_native",
            "plan_pgplan",
            "plan_outer_yan",
            "outer_yan_decision",
        ):
            snapshot = out / "correctness/sealed_context/{}.snapshot".format(name)
            self.assertTrue(snapshot.is_file(), name)
            self.assertEqual(
                receipt_values["context_{}_sha256".format(name)],
                hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            )
        # The later timing error must not erase completed correctness evidence.
        self.assertNotIn("status", manifest)

    def test_performance_only_mode_reuses_fresh_target_receipt(self) -> None:
        first, source = self.run_experiment(
            out_name="fresh", FAKE_DUCK_TIMING_FAILURE="1"
        )
        self.assertEqual(first.returncode, 1, first.stderr)
        database_sha = hashlib.sha256(self.database.read_bytes()).hexdigest()
        binary_sha = hashlib.sha256(self.duckdb.read_bytes()).hexdigest()
        copied_plan = self.root / "copied-plan.json"
        shutil.copy2(self.plan, copied_plan)
        call_log = self.root / "reuse-calls.tsv"
        second, out = self.run_experiment(
            extra_args=(
                "--plan",
                str(copied_plan),
                "--comparison-mode",
                "none",
                "--reuse-correctness-from",
                str(source),
                "--execution-db-sha256",
                database_sha.upper(),
                "--duckdb-bin-sha256",
                binary_sha.upper(),
            ),
            out_name="reused",
            FAKE_DUCK_CALL_LOG=str(call_log),
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("no correctness query executed now", second.stdout)
        kinds = [
            line.split("\t", 1)[0]
            for line in call_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(kinds.count("correctness"), 0)
        self.assertEqual(kinds.count("timing"), 3)
        self.assertEqual(kinds.count("explain"), 3)
        manifest = dict(
            line.split("=", 1)
            for line in (out / "provenance/manifest.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(manifest["correctness_origin"], "REUSED")
        self.assertEqual(manifest["correctness_status"], "PASS")
        self.assertEqual(manifest["correctness_comparison_executed"], "0")
        self.assertEqual(manifest["correctness_comparison_set"], "none")
        self.assertEqual(manifest["comparison_mode"], "none")
        self.assertEqual(manifest["correctness_scope"], "target")
        self.assertEqual(manifest["correctness_reuse_source"], str(source.resolve()))
        self.assertEqual(manifest["execution_db_sha256_source"], "provided")
        self.assertEqual(manifest["duckdb_bin_sha256_source"], "provided")
        self.assertEqual(
            (out / "correctness/receipt.txt").read_bytes(),
            (source / "correctness/receipt.txt").read_bytes(),
        )
        self.assertTrue((out / "correctness/reuse.txt").is_file())
        self.assertTrue(
            (out / "correctness/sealed_context/outer_yan_decision.snapshot").is_file()
        )
        self.assertFalse((out / "correctness/native.csv").exists())
        for summary_name in ("summary.tsv",):
            with (out / "timing" / summary_name).open(
                newline="", encoding="utf-8"
            ) as source_file:
                summary_rows = list(csv.DictReader(source_file, delimiter="\t"))
            self.assertEqual(
                [row["configuration"] for row in summary_rows],
                ["native", "pgplan", "outer_yan"],
                summary_name,
            )
            self.assertTrue(
                all(row["median_seconds"] == "0.001000000" for row in summary_rows),
                (summary_name, summary_rows),
            )
            self.assertTrue(
                all(row["measured_runs"] == "1" for row in summary_rows),
                (summary_name, summary_rows),
            )
            self.assertTrue(
                all(row["threads"] == "16" for row in summary_rows),
                (summary_name, summary_rows),
            )

    def test_reuse_rejects_tampered_correctness_evidence_fail_closed(self) -> None:
        fresh, source = self.run_experiment(out_name="fresh")
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        (source / "correctness/pgplan.comparison.txt").write_text(
            "PASS native == pgplan\ntampered\n", encoding="utf-8"
        )
        call_log = self.root / "tampered-calls.tsv"
        reused, _out = self.run_experiment(
            extra_args=("--reuse-correctness-from", str(source)),
            out_name="reused",
            FAKE_DUCK_CALL_LOG=str(call_log),
        )
        self.assertEqual(reused.returncode, 1, reused.stderr)
        self.assertIn("correctness reuse evidence validation failed", reused.stderr)
        kinds = [
            line.split("\t", 1)[0]
            for line in call_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertNotIn("correctness", kinds)
        self.assertNotIn("timing", kinds)

    def test_reuse_rejects_bounded_correctness_receipt(self) -> None:
        bounded_db = self.root / "bounded.db"
        bounded_db.touch()
        fresh, source = self.run_experiment(
            extra_args=("--correctness-db", str(bounded_db)), out_name="bounded"
        )
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        self.assertFalse((source / "correctness/receipt.txt").exists())
        self.assertTrue((source / "correctness/unsealed.txt").is_file())
        reused, _out = self.run_experiment(
            extra_args=("--reuse-correctness-from", str(source)),
            out_name="reused",
        )
        self.assertEqual(reused.returncode, 1, reused.stderr)
        self.assertIn("correctness reuse evidence validation failed", reused.stderr)

    def test_reuse_rejects_changed_target_database_fingerprint(self) -> None:
        fresh, source = self.run_experiment(out_name="fresh")
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        self.database.write_bytes(b"changed after correctness\n")
        reused, _out = self.run_experiment(
            extra_args=("--reuse-correctness-from", str(source)),
            out_name="reused",
        )
        self.assertEqual(reused.returncode, 1, reused.stderr)
        self.assertIn("correctness reuse evidence validation failed", reused.stderr)

    def test_reuse_rejects_changed_correctness_thread_count(self) -> None:
        fresh, source = self.run_experiment(out_name="fresh")
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        reused, _out = self.run_experiment(
            extra_args=(
                "--threads",
                "2",
                "--reuse-correctness-from",
                str(source),
            ),
            out_name="reused",
        )
        self.assertEqual(reused.returncode, 1, reused.stderr)
        self.assertIn("correctness reuse evidence validation failed", reused.stderr)

    def test_reuse_rejects_changed_statement_timeout_setting(self) -> None:
        fresh, source = self.run_experiment(out_name="fresh")
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        reused, _out = self.run_experiment(
            extra_args=("--reuse-correctness-from", str(source)),
            out_name="reused",
            PGPLAN_TIMEOUT_SECS="2",
        )
        self.assertEqual(reused.returncode, 1, reused.stderr)
        self.assertIn("correctness reuse evidence validation failed", reused.stderr)

    def test_reuse_rejects_changed_full_outer_yan_decision_trace(self) -> None:
        fresh, source = self.run_experiment(out_name="fresh")
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        reused, _out = self.run_experiment(
            extra_args=("--reuse-correctness-from", str(source)),
            out_name="reused",
            FAKE_OY_DECISION_EXTRA=" reason=SAME_SELECTION_DIFFERENT_CONTEXT",
        )
        self.assertEqual(reused.returncode, 1, reused.stderr)
        self.assertIn("correctness reuse evidence validation failed", reused.stderr)

    def test_direct_database_fingerprint_rejects_nonempty_wal(self) -> None:
        Path(str(self.database) + ".wal").write_bytes(b"active")
        call_log = self.root / "wal-calls.tsv"
        result, _out = self.run_experiment(FAKE_DUCK_CALL_LOG=str(call_log))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("nonempty WAL", result.stderr)
        self.assertFalse(call_log.exists())

    def test_precomputed_fingerprints_require_exact_sha256_syntax(self) -> None:
        result, _out = self.run_experiment(
            extra_args=("--execution-db-sha256", "abc"),
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("must be exactly 64 hexadecimal characters", result.stderr)

    def test_only_multithread_batch_runs_with_requested_measurements(self) -> None:
        result, out = self.run_experiment(extra_args=("--runs", "3"))
        self.assertEqual(result.returncode, 0, result.stderr)
        with (out / "timing/summary.tsv").open(
            newline="", encoding="utf-8"
        ) as source:
            tm_rows = list(csv.DictReader(source, delimiter="\t"))
        self.assertTrue(all(row["measured_runs"] == "3" for row in tm_rows))
        self.assertTrue(all(row["threads"] == "16" for row in tm_rows))
        self.assertEqual(
            (out / "timing/native.log").read_text(encoding="utf-8").count(
                "Run Time"
            ),
            4,
        )
        self.assertFalse(list((out / "timing").glob("t1_*")))

    def test_three_way_timing_contract_matches_original_harness(self) -> None:
        three_way = EXPERIMENT.read_text(encoding="utf-8")
        original = (SCRIPT_DIR.parent / "experiment_onoff.sh").read_text(
            encoding="utf-8"
        )
        for token in (".mode trash", "CALL disable_profiling();", ".timer on"):
            self.assertIn(token, three_way)
            self.assertIn(token, original)
        self.assertIn("emit_bare_query", three_way)
        self.assertIn('${query%;};', original)
        self.assertNotIn('run_timing_suite timing_t1', three_way)

    def test_correctness_database_cli_overrides_environment(self) -> None:
        environment_db = self.root / "environment-correctness.db"
        environment_db.touch()
        cli_db = self.root / "cli-correctness.db"
        cli_db.touch()
        call_log = self.root / "database-override-calls.tsv"
        result, _out = self.run_experiment(
            extra_args=("--correctness-db", str(cli_db)),
            PGPLAN_CORRECTNESS_DB=str(environment_db),
            FAKE_DUCK_CALL_LOG=str(call_log),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_database_routing(call_log, cli_db)

    def test_missing_correctness_database_fails_before_execution(self) -> None:
        missing = self.root / "missing-correctness.db"
        call_log = self.root / "missing-database-calls.tsv"
        result, _out = self.run_experiment(
            extra_args=("--correctness-db", str(missing)),
            FAKE_DUCK_CALL_LOG=str(call_log),
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("correctness database does not exist", result.stderr)
        self.assertFalse(call_log.exists())

    def test_csv_framing_timeout_is_skipped(self) -> None:
        python_wrapper = self.write_tool(
            "python-wrapper",
            r"""
            #!/usr/bin/env python3
            import os
            from pathlib import Path
            import sys
            import time

            if len(sys.argv) > 1 and Path(sys.argv[1]).name == "csv_records.py":
                time.sleep(5)
                raise SystemExit(0)
            os.execv(sys.executable, [sys.executable] + sys.argv[1:])
            """,
        )
        result, out = self.run_experiment(PYTHON_BIN=str(python_wrapper))
        self.assert_postprocess_timeout(
            result, out, "correctness_frame", "native"
        )

    def test_external_sort_timeout_is_skipped(self) -> None:
        self.write_tool(
            "sort",
            """
            #!/usr/bin/env python3
            import time
            time.sleep(5)
            """,
        )
        result, out = self.run_experiment()
        self.assert_postprocess_timeout(
            result, out, "correctness_sort", "native"
        )

    def test_row_count_timeout_is_skipped(self) -> None:
        self.write_tool(
            "wc",
            """
            #!/usr/bin/env python3
            import time
            time.sleep(5)
            """,
        )
        result, out = self.run_experiment()
        self.assert_postprocess_timeout(
            result, out, "correctness_count", "native"
        )

    def test_comparison_timeout_is_skipped(self) -> None:
        self.write_tool(
            "cmp",
            """
            #!/usr/bin/env python3
            import time
            time.sleep(5)
            """,
        )
        result, out = self.run_experiment()
        self.assert_postprocess_timeout(
            result, out, "correctness_compare", "pgplan"
        )

    def test_multiset_hash_timeout_is_skipped(self) -> None:
        self.write_tool(
            "sha256sum",
            r"""
            #!/usr/bin/env python3
            import hashlib
            from pathlib import Path
            import sys
            import time

            path = Path(sys.argv[-1])
            if path.name == "native.sorted.records.jsonl":
                time.sleep(5)
                raise SystemExit(0)
            print("{}  {}".format(hashlib.sha256(path.read_bytes()).hexdigest(), path))
            """,
        )
        result, out = self.run_experiment()
        self.assert_postprocess_timeout(
            result, out, "correctness_hash", "native"
        )

    def test_non_timeout_sort_failure_remains_failure(self) -> None:
        self.write_tool(
            "sort",
            """
            #!/usr/bin/env python3
            raise SystemExit(9)
            """,
        )
        result, _out = self.run_experiment()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("[PGPLAN] TIMEOUT", result.stderr)
        self.assertIn("external sort failed", result.stderr)

    def test_mismatch_diagnostic_is_bounded_but_remains_failure(self) -> None:
        self.write_tool(
            "cmp",
            r"""
            #!/usr/bin/env python3
            from pathlib import Path
            import sys
            import time

            if "-s" in sys.argv[1:]:
                left = Path(sys.argv[-2]).read_bytes()
                right = Path(sys.argv[-1]).read_bytes()
                raise SystemExit(0 if left == right else 1)
            time.sleep(5)
            """,
        )
        result, out = self.run_experiment(FAKE_DUCK_MISMATCH_PGPLAN="1")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("[PGPLAN] TIMEOUT", result.stderr)
        self.assertIn("result multiset mismatch", result.stderr)
        status = out / "correctness/pgplan.diff.status.txt"
        self.assertIn("exceeded 1s", status.read_text(encoding="utf-8"))

    def test_pgplan_only_mismatch_fails_before_timing(self) -> None:
        call_log = self.root / "partial-mismatch-calls.tsv"
        result, out = self.run_experiment(
            extra_args=("--comparison-mode", "pgplan-only"),
            FAKE_DUCK_MISMATCH_PGPLAN="1",
            FAKE_DUCK_CALL_LOG=str(call_log),
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("result multiset mismatch", result.stderr)
        kinds = [
            line.split("\t", 1)[0]
            for line in call_log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(kinds.count("correctness"), 2)
        self.assertEqual(kinds.count("timing"), 0)
        self.assertTrue((out / "correctness/pgplan.diff").is_file())
        self.assertFalse((out / "correctness/receipt.txt").exists())


if __name__ == "__main__":
    unittest.main()
