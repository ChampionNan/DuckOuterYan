# PGPlan: PostgreSQL typed logical join baseline

PGPlan reports the target-data planning and timing result as:

> PostgreSQL 16.2's plan-data-selected logical join tree, executed by DuckDB
> on the target-scale dataset.

That sentence does not describe the correctness dataset. Exact result equality
is checked separately on a bounded small DuckDB database; target data is
used for EXPLAIN, semantic-signature verification, and timing. PostgreSQL never
executes the result query.

Only PostgreSQL's base-table occurrences, exact binary grouping, child
orientation, and `INNER`/`LEFT`/`RIGHT`/`FULL` semantics are transferred.
PostgreSQL predicate text is retained only as diagnostic metadata. DuckDB
reuses the original query's already-bound predicates, filters, projections,
and root cap, then selects its own physical join operators. PGPlan therefore
does not execute PostgreSQL's physical plan.

The canonical commands live under `auto_test/pgplan/`. This implementation
directory keeps its historical name only so existing automation and internal
includes continue to work.

## One-command corpus workflow

From the repository root, no Docker setting is required:

```sh
bash auto_test/run_all.sh
```

The default `RUN_PGPLAN=1` workflow:

1. builds or reuses the release DuckDB binary and target DuckDB databases;
2. builds, installs, initializes, and starts the pinned PostgreSQL 16.2 source
   distribution under the repository if the managed binary is absent;
3. prepares minimal PostgreSQL plan-selection data;
4. builds one bounded DuckDB correctness database per selected
   family from the target catalog;
5. captures one fresh PGPlan artifact per selected SQL file with plain
   `EXPLAIN`; and
6. compares native DuckDB, PGPlan, and normal OuterYan exactly on the small
   correctness database, then verifies plans and times them on target data.

The default corpus is all 206 queries under `auto_test/outerjoin_query`:

| Family | Queries | PostgreSQL plan-selection data | DuckDB exact-correctness data |
|---|---:|---|---|
| graph | 7 | `pgplan_graph`, at most 1000 rows per table | deterministic `ORDER BY rowid` prefix, 500 rows per table |
| TPC-H | 54 | `public`, exact SF0.01 | `dbgen` SF0.01 |
| TPC-DS | 63 | `pgplan_tpcds`, at most 1000 rows per table | `dsdgen` SF0.01, with bounded target-rowid witnesses |
| JOB | 82 | `pgplan_job`, at most 1000 rows per table | deterministic `ORDER BY rowid` base prefix, 1000 rows per table, with bounded captured target-rowid witnesses |

Set `PGPLAN_SAMPLE_ROWS` to change the graph/TPC-DS/JOB row cap. The sampled
schemas reproduce compatible DuckDB column types, nullability, and exposed
primary/unique constraints, verify every loaded cardinality, and run `ANALYZE`.
The JOB parquet import represents 14 nullable, conceptually integral IMDb
columns as `DOUBLE`; the loader restores those reviewed columns to `BIGINT`
only after every sampled non-NULL value passes an exact round-trip check. The
manifest records each such coercion. These small PostgreSQL datasets choose the
tree only. PostgreSQL receives neither `EXPLAIN ANALYZE` nor any
result-producing query.

The correctness builder clones the target DuckDB table definitions,
nullability, and primary/unique keys. It validates every table cardinality and
each selected query against a bounded count before publishing the database and
its TSV manifest. TPC-DS and JOB collect a configurable number of bounded
target result-row witnesses per query when available so a target-nonempty query
remains nonempty after sampling; this is not a claim that every fixture or
corpus result is nonempty.
The rowid prefixes and SF0.01 generator bases are deterministic. Witness rows
are captured from the current target execution, so a witness-enriched fixture
is not claimed to be byte-identical across engines or runs.
The corpus runner records SHA-256 fingerprints of the exact published database
and builder manifest and copies both records into every query's provenance.
The defaults are controlled by `PGPLAN_CORRECTNESS_GRAPH_ROWS=500`,
`PGPLAN_CORRECTNESS_JOB_ROWS=1000`,
`PGPLAN_CORRECTNESS_MAX_RESULT_ROWS=2000000`, and
`PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS=30`.

Use the corpus options to run a bounded subset:

```sh
bash auto_test/run_all.sh --only tpcds --pattern '*q72*' --limit 1 --runs 1
```

Selection order is graph, TPC-H, TPC-DS, then JOB; file order is bytewise and
deterministic. `--limit` is global. Each selected query receives one row in
`status.tsv`. A row is `PASS` only after capture, PGPlan application, complete
small-database multiset comparison, target-database plan verification, and
target-database timing succeed. Setup, family preparation, capture, and
execution failures are recorded with their phase; remaining queries continue.
A PostgreSQL plain-`EXPLAIN` timeout or a DuckDB execution timeout is `SKIP`,
while every other failure is `FAIL` and makes the corpus command return
nonzero. PGPlan never falls back to DuckDB's native tree.

PostgreSQL plan capture defaults to 60 seconds
(`PGPLAN_CAPTURE_TIMEOUT_SECS` or `--capture-timeout`). DuckDB execution uses a
separate limit (`PGPLAN_TIMEOUT_SECS` or `--timeout`), which is applied to each
DuckDB statement and each potentially large correctness step (CSV framing,
sorting, counting, comparison, and hashing) and defaults to the main harness's
1800 seconds. Set either limit to `0` to disable it. A capture timeout writes no
artifact and never starts the three-way experiment; an execution or
post-processing timeout stops that query's remaining configurations and
timing, retains its diagnostic directory, and moves to the next query.

Correctness-database construction has its own fail-closed preflight controls:
`PGPLAN_CORRECTNESS_MAX_RESULT_ROWS` bounds every complete query result and
`PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS` bounds each validation query. These
limits prevent an unexpectedly explosive fixture from reaching CSV
materialization; they are independent of both PostgreSQL capture time and the
later DuckDB experiment timeout.

### PostgreSQL providers

`PGPLAN_SETUP=source` is the default. It checks the configured repo-local
`postgres/postgresql/bin/postgres`, not an arbitrary host PostgreSQL install.
When absent, setup downloads the official 16.2 source archive, verifies its
pinned SHA-256, configures and compiles it, installs it under
`postgres/postgresql`, initializes `postgres/postgresql/data`, and starts the
managed server at `127.0.0.1:55432`. A later run reuses that installation and
cluster. Source mode accepts only a loopback `PGPLAN_HOST` (`127.0.0.1`, `::1`,
or `localhost`), uses peer authentication for local sockets and SCRAM-SHA-256
for host connections, and verifies that an invalid password is rejected. With
no password override, `configs.sh` creates one random per-installation secret
at `postgres/postgresql/.pgplan-password` with mode `0600`; it is never printed.
Setup securely upgrades a cluster created by the earlier trust-authentication
version after first verifying that the endpoint owns the configured data
directory. Source mode requires a non-root account, a C toolchain, `make`,
`patch`, `tar`, a SHA-256 utility, and `curl` or `wget`; network is needed only
when the verified archive is not cached.

Docker is optional. It is useful when the server does not have the source-build
prerequisites. Like source mode, it generates and reuses the private
mode-`0600` secret at `PGPLAN_PASSWORD_FILE` unless a password is explicitly
provided:

```sh
PGPLAN_SETUP=docker bash auto_test/run_all.sh
```

If a container created by an older setup uses a different password, setup
fails with a recreate-or-current-password instruction instead of silently
using or replacing that container.

An existing PostgreSQL 16.2 server can be selected explicitly:

```sh
PGPLAN_SETUP=external \
PG_DSN='host=127.0.0.1 port=5432 dbname=duckyan_tpch user=postgres' \
PSQL_BIN=/absolute/path/to/psql \
bash auto_test/run_all.sh
```

External mode must already contain the exact public TPC-H SF0.01 tables unless
`PGPLAN_FORCE_DATA=1` authorizes their replacement. It also needs permission to
create the isolated sampled schemas. Replacing existing sampled schemas in
external mode requires `PGPLAN_FORCE_SAMPLED_DATA=1`.

`SKIP_DATA=1` skips only target DuckDB database generation; it does not skip
PostgreSQL setup or its minimal plan-selection data. `SKIP_PG_DATA=1` forbids
TPC-H loading/repair and requires the exact SF0.01 cardinalities to be present.
`RUN_PGPLAN=0` selects the historical two-configuration DuckDB/OuterYan
workflow.

## Manual plan-data preparation

Prepare only the managed PostgreSQL server and exact TPC-H SF0.01 data:

```sh
bash auto_test/pgplan/setup_pg.sh
```

The source build follows the repository-local layout used by the
[Quorion reproducibility launcher](https://github.com/hkustDB/Quorion/blob/reproducibility/scripts/run_all_1.sh).
It disables optional ICU, readline, and zlib integration to remain usable on a
minimal server. A pinned compatibility patch resolves a PostgreSQL 16.2
`strchrnul` fallback collision with newer macOS SDK headers without changing
planner or server behavior.

For low-level TPC-H preparation,
`prepare_tpch_pg.sh --pg-dsn DSN` accepts `--data-dir` or `--duckdb-bin`.
The eight files may use official `.tbl` text or pipe-delimited `.csv`.

Prepare one sampled family manually:

```sh
auto_test/pgplan/prepare_sampled_pg.sh \
  --family tpcds \
  --duckdb-db /absolute/path/to/tpcds_db \
  --rows 1000 \
  --pg-dsn "$PG_DSN" \
  --manifest /absolute/path/to/tpcds-sample.tsv
```

The PostgreSQL sample above is not the DuckDB correctness database. Build the
latter independently from the target DuckDB catalog:

```sh
auto_test/pgplan/prepare_correctness_db.sh \
  --family tpcds \
  --source-db /absolute/path/to/tpcds_db \
  --out /absolute/path/to/tpcds-correctness.duckdb \
  --query-dir /absolute/path/to/outerjoin_query/tpcds \
  --max-result-rows 2000000 \
  --query-timeout 30 \
  --manifest /absolute/path/to/tpcds-correctness.tsv
```

`--source-db` is the schema authority and the source of bounded TPC-DS/JOB
rowid witnesses; it remains the target database used later for plans and
timing. `--rows` changes only the graph or JOB physical-row prefix (defaults
500 and 1000); TPC-H and TPC-DS always use their SF0.01 generators. The builder
publishes the database and manifest only after schema, key, data, and query
bound validation succeeds. `--force` atomically replaces existing outputs.

## Capture and normalize a plan

TPC-H uses the default `public`/`tpch-sf0.01` provenance:

```sh
auto_test/pgplan/make_plan.sh \
  --query /absolute/path/to/query.sql \
  --out /absolute/path/to/query.pg.json
```

For another family, name the isolated schema and its exact row-cap label:

```sh
auto_test/pgplan/make_plan.sh \
  --pg-schema pgplan_tpcds \
  --plan-data tpcds-duckdb-sample-1000 \
  --query /absolute/path/to/query.sql \
  --out /absolute/path/to/query.pg.json
```

Defaults come from `auto_test/configs.sh`; explicit CLI options take
precedence. Capture requires `server_version_num=160002` and PostgreSQL's
compiled defaults for every `Query Tuning` setting. Its only plan-setting
override is `max_parallel_workers_per_gather=0`; a sampled family also uses the
exact deterministic `search_path=<family schema>, pg_catalog`. The query is
sent only to:

```sql
EXPLAIN (FORMAT JSON, VERBOSE, COSTS TRUE, SETTINGS TRUE)
```

without `ANALYZE`, inside a read-only transaction. A dependency-free SQL
scanner rejects multiple statements before invoking `psql`. Capture also sets
a transaction-local `statement_timeout` (60 seconds by default); this only
bounds PostgreSQL optimizer wall time and is not a physical-plan execution.

The normalized artifact has this stable shape:

```json
{
  "format": "duckyan.pg_join_tree.v1",
  "query_sha256": "...",
  "query_sha256_canonicalization": "duckyan.sql_text.v1",
  "postgres": {
    "version_num": 160002,
    "settings": {
      "max_parallel_workers_per_gather": "0",
      "search_path": "pgplan_tpcds, pg_catalog"
    },
    "plan_schema": "pgplan_tpcds",
    "plan_data": "tpcds-duckdb-sample-1000"
  },
  "tree": {
    "op": "join",
    "join_type": "left",
    "left": {
      "op": "scan",
      "schema": "public",
      "relation": "store_sales",
      "alias": "ss",
      "occurrence": 0
    },
    "right": {
      "op": "scan",
      "schema": "public",
      "relation": "store",
      "alias": "s",
      "occurrence": 0
    },
    "diagnostics": {}
  }
}
```

`Hash`, `Sort`, `Incremental Sort`, `Materialize`, and `Memoize` are transparent
physical wrappers. A root PostgreSQL `Aggregate` is retained as wrapper
diagnostics while the imported tree remains the join decision. `Hash Join`,
`Merge Join`, and `Nested Loop` become typed logical joins; PostgreSQL's
`Outer` child is artifact `left` and `Inner` child is artifact `right`.
Predicate strings remain under `diagnostics.predicates` and are never rebound
by DuckDB.

Every scan records relation, alias, and query occurrence. A repeated base table
is supported only when distinct aliases let the capture scanner recover each
occurrence deterministically. Unsupported plan nodes or join kinds, duplicate
aliases/occurrences, malformed child relationships, unexpected schemas, or
extra planner settings fail before an artifact is written. Source PostgreSQL
schemas are provenance; normalized scan schema `public` maps to DuckDB's
default `main` schema during import.

### Query hash

Capture and DuckDB use `duckyan.sql_text.v1` before SHA-256:

1. decode as UTF-8;
2. normalize CRLF and lone CR to LF;
3. remove leading ASCII whitespace plus leading line/block comments (including
   nested block comments), matching the statement text DuckDB exposes;
4. remove one optional terminal semicolon, then trim trailing whitespace; and
5. preserve every other byte, including comments after the first SQL token,
   case, and interior spacing.

The artifact format is not yet released, so this capture/import alignment fix
remains part of `duckyan.sql_text.v1` rather than introducing a second version.

Generate and load an artifact with the same SQL text. Semantically equivalent
rewrites intentionally do not share a hash.

## Apply PGPlan in DuckDB

The artifact path must be absolute:

```sql
SET VARIABLE pgplan = '/absolute/path/to/query.pg.json';
SELECT ...;
RESET VARIABLE pgplan;
```

When active, PGPlan:

1. validates the artifact version, plan-data/schema pairing, settings, query
   hash, and tree shape;
2. identifies DuckDB base-table occurrences and rebuilds PostgreSQL's imported
   binary splits;
3. redistributes every original DuckDB-bound join condition to its lowest
   valid imported join, without translating PostgreSQL predicate text;
4. verifies join kind and preserved/null-supplying orientation;
5. rebuilds the exact imported grouping and logical orientation; and
6. verifies the final semantic signature after later optimizer passes.

An original outer join may match PostgreSQL's `INNER` only when DuckDB's own
null-rejection analysis independently proves that reduction. If PostgreSQL
omits a null-supplying outer-join side, PGPlan accepts it only when the original
DuckDB query and target catalog independently prove the exact supported
single-base, unique-key elimination; any ambiguous or unproved omission is an
error.

PGPlan skips OuterYan, normal outer-join simplification, native join ordering,
independent join elimination, semi-join insertion, and aggregate pushdown.
DuckDB still selects physical algorithms and may perform a legal physical
build/probe swap with the corresponding `LEFT`/`RIGHT` semantic flip.
An otherwise conditionless imported `INNER` split may receive a plain
column-equality predicate only when it follows from the transitive closure of
the original DuckDB-bound equalities. The diagnostic reports the number of
such `implied_equality_count` predicates. No predicate is synthesized for an
outer join. Successful optimization emits machine-readable `[PGPLAN]`
imported and verified signatures. A missing leaf, unsafe split, changed
grouping, changed preserved side, or provenance mismatch throws instead of
falling back.

Plain `EXPLAIN SELECT ...` strips only its wrapper and verifies the same bare
query hash. `EXPLAIN ANALYZE`, non-plain EXPLAIN forms, explicitly prepared
execution, and disabling DuckDB's optimizer while PGPlan is active are rejected
when they could bypass validation.

### Supported semantic scope

PGPlan v1 accepts a connected, acyclic comparison-join skeleton. Every
original logical join needs a stable, non-throwing equality anchor whose two
expression sides each resolve to exactly one base relation; this includes safe
implicit casts. Stable theta and unary/non-comparison `ON` residuals are
retained and placed at their lowest valid imported join. They may not be moved
from an inner join into an outer join's `ON` scope. A conditionless imported
inner split is accepted only when the original plain column equalities
independently imply a safe equality across that split. Root projections and
filters, one bound root aggregate/distinct cap, and repeated base tables with
distinct aliases are supported.

The following remain fail-closed: cross products; cyclic join graphs; CTEs;
subqueries and table-valued sources; set, window, ASOF, positional, semi, anti,
mark, and single joins; aggregates inside the join skeleton; residuals that
cannot be placed without changing an outer-join `ON` scope; and volatile or
throwing conditions whose evaluation scope cannot be reproduced. Arbitrary
PostgreSQL expression translation is not part of PGPlan.

## Three-configuration experiment

Run one prepared query manually:

```sh
auto_test/pgplan/experiment.sh \
  --duckdb-bin /absolute/path/to/release/duckdb \
  --execution-db /absolute/path/to/tpch_db \
  --correctness-db /absolute/path/to/tpch-correctness.duckdb \
  --query /absolute/path/to/query.sql \
  --plan /absolute/path/to/query.pg.json \
  --runs 3 --threads 16 \
  --out /absolute/path/to/results
```

For a bounded corpus run where both planning and each DuckDB statement may use
at most 60 seconds:

```sh
bash auto_test/run_all.sh --capture-timeout 60 --timeout 60
```

`--correctness-db` (or `PGPLAN_CORRECTNESS_DB`) selects the database used only
for the three exact result checks. It defaults to `--execution-db` for manual
backward compatibility; the corpus workflow always supplies its generated
small database explicitly.

The harness executes the bare query once as native DuckDB, PGPlan, and normal
OuterYan on the correctness database. It externally sorts and compares those
three complete result multisets. The execution database supplies all three
EXPLAIN plans and semantic diagnostics; only after exact equality passes does
the harness time one warm-up plus the requested odd number of measured
release-build runs there in output-discarding mode. It saves plans, traces,
settings, both database paths, artifact provenance, correctness row counts, and
multiset hashes. Corpus runs also retain the correctness builder manifest and
database/manifest SHA-256 fingerprints per query. The corpus runner removes
bulky correctness CSVs after a successful comparison by default while
retaining those hashes.

OuterYan remains its normal cost-gated configuration and may legitimately
select DuckDB's candidate. The manifest records `outer_yan_selected_plan`, so
three configurations are not mislabeled as three distinct logical trees.

The harness uses only shell tools and the Python standard library; it requires
Python 3.7 or newer, no pip packages, and no Docker runtime. Set `PYTHON_BIN`
to an absolute repo-local interpreter when the system `python3` should not be
used; `run_all.sh` validates that interpreter before starting setup.

### Claim boundary

A successful run proves complete multiset equality among native DuckDB,
PGPlan, and OuterYan on the captured small correctness database. The same
immutable PGPlan artifact is applied there and to the target database. The
target-data EXPLAIN and `[PGPLAN]` semantic signature prove that DuckDB accepted
and preserved the imported typed grouping on target data, and target-data
timings measure DuckDB's physical execution of that logical tree. The run does
not compare complete target-scale result multisets, does not execute a
PostgreSQL physical plan, and does not claim that PostgreSQL would choose the
same tree with target-scale statistics. The artifact remains the tree
PostgreSQL chose from its recorded minimal plan-selection data.

## Compatibility and tests

Previous `PG_REPLAY_*` environment spellings and the
`outer_yan_pg_replay_plan` SQL variable are accepted only as compatibility
inputs. New commands, variables, logs, diagnostics, modes, and result labels use
`PGPlan`/`PGPLAN_*`/`pgplan`.

```sh
python3 -m unittest discover -s auto_test/postgres_replay -p 'test_*.py' -v
bash -n auto_test/pgplan/*.sh auto_test/run_all.sh auto_test/configs.sh
```
