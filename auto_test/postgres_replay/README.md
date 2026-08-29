# PGPlan: PostgreSQL typed logical join baseline

PGPlan reports the target-data planning and timing result as:

> PostgreSQL 16.2's plan-data-selected logical join tree, executed by DuckDB
> on the target-scale dataset.

By default, exact result equality is also checked on that target DuckDB
database. PostgreSQL itself never executes the result query.

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

PGPlan is excluded from the normal `run_all.sh` workflow. Opt in explicitly;
no Docker setting is required for the default source provider:

```sh
RUN_PGPLAN=1 bash auto_test/run_all.sh
```

The default persistent artifact cache is `auto_test/pgplan/plans`. The corpus
runner validates every candidate there before starting PostgreSQL. Validation
binds the artifact and its sidecar to the canonical query hash, artifact
SHA-256, PostgreSQL 16.2 settings, the configured family schema/data label, the
exact bounded plan-selection sample, one statistics epoch, and a connected
typed binary tree. Any miss or mixed epoch recaptures all selected queries in
that family with plain `EXPLAIN` after one new `ANALYZE`; fully cached families
do not start PostgreSQL. Each run also receives an immutable artifact copy.
Set `PGPLAN_PLAN_CACHE` or pass `--plan-cache DIR` to choose another location.

Correctness modes are manual and do not change EXPLAIN or timing work:

```sh
# PGPlan mode: Original == PGPlan, and Original == OuterYan
RUN_PGPLAN=1 bash auto_test/run_all.sh

# Only Original == PGPlan
RUN_PGPLAN=1 bash auto_test/run_all.sh --skip1

# No correctness queries; performance and plan verification only
RUN_PGPLAN=1 bash auto_test/run_all.sh --performance-only
```

`--skip2`, `--performance_only`, and the accepted compatibility misspelling
`--performace_only` select the same no-correctness mode. It records `NOT_RUN`
rather than claiming that an old comparison still applies. The stricter
`--reuse-from` path remains available when prior correctness must be validated
from its sealed receipt.

The opt-in `RUN_PGPLAN=1` workflow:

1. builds or reuses the release DuckDB binary and target DuckDB databases;
2. validates persistent typed artifacts for all selected queries;
3. only when there are cache misses, builds/starts pinned PostgreSQL 16.2 and
   prepares the required minimal plan-selection data;
4. captures missing/stale PGPlan artifacts with plain `EXPLAIN` and publishes
   them to the cache; and
5. performs the requested correctness mode, then records independent Original,
   PGPlan, and OuterYan TM and T1 timing batches on target data.

The default corpus is all 206 queries under `auto_test/outerjoin_query`:

| Family | Queries | PostgreSQL plan-selection data | DuckDB exact-correctness data |
|---|---:|---|---|
| graph | 7 | `pgplan_graph`, at most 1000 rows per table | configured target graph DB |
| TPC-H | 54 | `public`, exact SF0.01 | configured target TPC-H DB |
| TPC-DS | 63 | `pgplan_tpcds`, at most 1000 rows per table | configured target TPC-DS DB |
| JOB | 82 | `pgplan_job`, at most 1000 rows per table | configured target JOB DB |

Set `PGPLAN_SAMPLE_ROWS` to change the graph/TPC-DS/JOB row cap. The sampled
schemas reproduce compatible DuckDB column types, nullability, and exposed
primary/unique constraints, verify every loaded cardinality, and run `ANALYZE`.
The JOB parquet import represents 14 nullable, conceptually integral IMDb
columns as `DOUBLE`; the loader restores those reviewed columns to `BIGINT`
only after every sampled non-NULL value passes an exact round-trip check. The
manifest records each such coercion. These small PostgreSQL datasets choose the
tree only. PostgreSQL receives neither `EXPLAIN ANALYZE` nor any
result-producing query.

`PGPLAN_CORRECTNESS_MODE=bounded` is an explicit quicker diagnostic mode. In
that mode, the correctness builder clones the target DuckDB table definitions,
nullability, and primary/unique keys. It validates every table cardinality and
each selected query against a bounded count before publishing the database and
its TSV manifest. TPC-DS and JOB collect a configurable number of bounded
target result-row witnesses per query when available so a target-nonempty query
remains nonempty after sampling; this is not a claim that every fixture or
corpus result is nonempty.
The rowid prefixes and SF0.01 generator bases are deterministic. Witness rows
are captured from the current target execution, so a witness-enriched fixture
is not claimed to be byte-identical across engines or runs.
The bounded-mode corpus runner records SHA-256 fingerprints of the published database
and builder manifest and copies both records into every query's provenance.
The bounded-mode defaults are controlled by `PGPLAN_CORRECTNESS_GRAPH_ROWS=500`,
`PGPLAN_CORRECTNESS_JOB_ROWS=1000`,
`PGPLAN_CORRECTNESS_MAX_RESULT_ROWS=2000000`, and
`PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS=30`.

### Performance reruns with sealed correctness

After one successful default target-mode corpus, repeat only plan verification
and performance with:

```sh
RUN_PGPLAN=1 bash auto_test/run_all.sh \
  --reuse-from /absolute/path/to/prior/pgplan_corpus_YYYYMMDD_HHMMSS
```

`--reuse-from` is the canonical one-parameter rerun mode. `run_all.sh`
automatically skips build, target-data generation, and query regeneration so
the prior fingerprints cannot be invalidated. The corpus runner also skips
PostgreSQL setup, sampled PostgreSQL loading, and plain-EXPLAIN capture. For
each selected query it safely resolves and copies the prior PGPlan artifact,
validates the sealed target-scale correctness receipt, and then runs the same
Native/PGPlan/OuterYan EXPLAIN, importer verification, TM, and T1 phases into a
new result directory.

Reuse is fail-closed and never silently performs fresh correctness or selects a
native plan. The receipt is accepted only when its query bytes, PGPlan artifact,
DuckDB binary and version, and target database SHA-256 values match. The binary
is hashed once per corpus and each selected family database once; target runs
record the same hashes so they can become future sources. A non-empty or unsafe
DuckDB `.wal`, a missing/stale receipt or artifact, or a symlink/path escape is
recorded as that query's failure and the remaining queries continue. The copied
artifact and receipt provenance make the new result self-contained.

The lower-level correctness-only variant is:

```sh
RUN_PGPLAN=1 \
PGPLAN_CORRECTNESS_MODE=reuse \
PGPLAN_CORRECTNESS_FROM=/absolute/path/to/prior/pgplan_corpus_YYYYMMDD_HHMMSS \
  bash auto_test/run_all.sh
```

That variant reuses correctness receipts but still sets up PostgreSQL and
captures fresh plans. `target` remains the default and performs a new complete
comparison; `bounded` remains only a diagnostic.

Use the corpus options to run a selected query subset:

```sh
RUN_PGPLAN=1 bash auto_test/run_all.sh --only tpcds --pattern '*q72*' --limit 1 --runs 1
```

Selection order is graph, TPC-H, TPC-DS, then JOB; file order is bytewise and
deterministic. `--limit` is global. Each selected query receives one row in
`status.tsv`. In the default mode, a row is `PASS` only after capture, PGPlan
application, complete target-database multiset comparison, target-database
plan verification, and target-database timing succeed. In reuse mode, the new
comparison is replaced only by validation of its sealed prior target receipt.
Setup, family preparation, capture, and
execution failures are recorded with their phase; remaining queries continue.
A PostgreSQL plain-`EXPLAIN` timeout or a DuckDB execution timeout is `SKIP`,
while every other failure is `FAIL`. Either status makes the corpus command
return nonzero, so success requires every selected query to complete. PGPlan
never falls back to DuckDB's native tree.

Despite the historical PGPlan name, this corpus command performs all three
DuckDB configurations for every successful query: Native, imported PGPlan,
and normal OuterYan. Each successful run retains its three TM medians in
`runs/<family>/<query>/timing/summary.tsv` and its three single-thread medians
in `timing/t1_summary.tsv`. Before returning success or failure,
the corpus runner produces `comparison.tsv` and `comparison.csv` with one row
per selected query, a human-readable `comparison.log`, `summary.tsv` with
overall and per-family aggregate speedups, and `failures.tsv` with all
`FAIL`/`SKIP` rows. Every normal PASS/FAIL/SKIP is streamed immediately as a
legacy-style, separator-delimited block and retained in `comparison.log`.
Those blocks are rendered from the same ordered records as `comparison.tsv`
and `comparison.csv`, keeping the detailed and tabular outputs in parity.
Incomplete rows never inherit partial timing output.

The CSV/TSV begins with the complete `experiment_onoff.sh` header in its
original order and with its original meanings. Existing two-way analysis can
therefore ignore every later column. Every appended field includes `pgplan` in
its name and covers verification, `tm_pgplan`, `t1_pgplan`, comparison
mode/status, or correctness provenance. Raw plan signatures remain in trace
artifacts and are not copied into the human log or CSV.

Correctness provenance is explicit. `pgplan_correctness_origin` distinguishes
`FRESH`, `PARTIAL`, `NOT_RUN`, and `REUSED`; the comparison-set and execution
columns state exactly which result checks ran. Reused rows additionally retain
their source and receipt SHA-256 values. Older artifacts leave new fields empty
rather than guessing an origin.

For completed performance, the original CSV's `TM:off/on` and `T1:off/on`
fields retain their Original/OuterYan meanings. Appended `tm_pgplan` and
`t1_pgplan` fields add PGPlan. Legacy Original/PGPlan speedup fields remain for
compatibility, while new PGPlan/OuterYan fields provide the direct comparison.
The human line orders times as Original, PGPlan, OuterYan and prints only
Original/OuterYan and PGPlan/OuterYan ratios; values above one favor OuterYan.
The workflow does not collect the legacy phase profile or semi-join kernel
trace. Their placeholders are omitted from the human log while the original
CSV columns remain empty/NA for compatibility. The original `rows` column is the complete target-database
result count by default. TM and T1 use `.mode trash`: DuckDB executes and fully
materializes the bare query, while CLI result serialization and filesystem
output are excluded from the real DuckDB CLI wall-clock timing.
The correctness-database selected-plan column is blank when summarizing a
legacy result produced before that provenance field existed.

Reports for an existing result directory can be generated without rerunning
any query:

```sh
bash auto_test/pgplan/summarize_corpus.sh \
  --result-dir /absolute/path/to/pgplan_corpus_YYYYMMDD_HHMMSS
```

This command regenerates `comparison.log` without recapturing plans or
repeating correctness and timing executions; use `less` or `cat` to display
the saved blocks.

PostgreSQL plan capture defaults to 300 seconds
(`PGPLAN_CAPTURE_TIMEOUT_SECS` or `--capture-timeout`). DuckDB execution uses a
separate limit (`PGPLAN_TIMEOUT_SECS` or `--timeout`), which is applied to each
DuckDB statement and each potentially large correctness step (CSV framing,
sorting, counting, comparison, and hashing) and defaults to the main harness's
1800 seconds. Set either limit to `0` to disable it. A capture timeout writes no
artifact and never starts that query's comparison/performance experiment; an
execution or
post-processing timeout stops that query's remaining configurations and
timing, retains its diagnostic directory, and moves to the next query. The
corpus still exits nonzero because at least one selected query was incomplete.

Bounded correctness-database construction has its own fail-closed preflight controls:
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
RUN_PGPLAN=1 PGPLAN_SETUP=docker bash auto_test/run_all.sh
```

If a container created by an older setup uses a different password, setup
fails with a recreate-or-current-password instruction instead of silently
using or replacing that container.

An existing PostgreSQL 16.2 server can be selected explicitly:

```sh
PGPLAN_SETUP=external \
PG_DSN='host=127.0.0.1 port=5432 dbname=duckyan_tpch user=postgres' \
PSQL_BIN=/absolute/path/to/psql \
RUN_PGPLAN=1 bash auto_test/run_all.sh
```

External mode must already contain the exact public TPC-H SF0.01 tables unless
`PGPLAN_FORCE_DATA=1` authorizes their replacement. It also needs permission to
create the isolated sampled schemas. Replacing existing sampled schemas in
external mode requires `PGPLAN_FORCE_SAMPLED_DATA=1`.

`SKIP_DATA=1` skips only target DuckDB database generation; it does not skip
PostgreSQL setup or its minimal plan-selection data. `SKIP_PG_DATA=1` forbids
TPC-H loading/repair and requires the exact SF0.01 cardinalities to be present.
The default `RUN_PGPLAN=0` selects the two-configuration DuckDB
Original/OuterYan workflow and performs no PostgreSQL setup, capture, import,
correctness, or timing work.

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
a transaction-local `statement_timeout` (300 seconds by default); this only
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
  --query /absolute/path/to/query.sql \
  --plan /absolute/path/to/query.pg.json \
  --runs 3 --threads 16 \
  --out /absolute/path/to/results
```

Add `--correctness-db /absolute/path/to/tpch-correctness.duckdb` only for an
explicit manual bounded-data check.

For a bounded corpus run where PostgreSQL planning may use five minutes and
each DuckDB statement may use at most 60 seconds:

```sh
PGPLAN_CORRECTNESS_MODE=bounded \
  RUN_PGPLAN=1 bash auto_test/run_all.sh --capture-timeout 300 --timeout 60
```

`--correctness-db` (or `PGPLAN_CORRECTNESS_DB`) selects the database used only
for the three result executions that support the two equality comparisons. It
defaults to `--execution-db` for manual and corpus runs. The corpus supplies a
generated small database only when
`PGPLAN_CORRECTNESS_MODE=bounded` is explicitly selected.

The harness executes the bare query once as native DuckDB, PGPlan, and normal
OuterYan on the correctness database. It externally sorts and compares those
three complete result multisets. The execution database supplies all three
EXPLAIN plans and semantic diagnostics; only after exact equality passes does
the harness run independent timing batches. TM has one warm-up plus the
requested odd number of measured release-build runs; T1 has one warm-up plus
exactly one measured run for each configuration. `.mode trash` fully
drains every bare query but excludes CLI result serialization and output I/O
from DuckDB's real wall-clock samples. It saves plans, traces,
settings, both database paths, artifact provenance, correctness row counts, and
multiset hashes. Bounded corpus runs also retain the correctness builder manifest and
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

A default successful run proves complete target-data multiset equality among
native DuckDB, PGPlan, and OuterYan. The target-data EXPLAIN and `[PGPLAN]`
semantic signature prove that DuckDB accepted and preserved the imported typed
grouping, and the target-data timings measure DuckDB's physical execution of
that logical tree. A bounded-mode PASS proves equality only on its recorded
small database. A reuse-mode PASS cites a sealed, matching prior target-mode
equality receipt instead of executing the result comparison again. No mode
executes a PostgreSQL physical plan or claims
that PostgreSQL would choose the same tree with target-scale statistics. The
artifact remains the tree PostgreSQL chose from its recorded minimal
plan-selection data.

## Compatibility and tests

Previous `PG_REPLAY_*` environment spellings and the
`outer_yan_pg_replay_plan` SQL variable are accepted only as compatibility
inputs. New commands, variables, logs, diagnostics, modes, and result labels use
`PGPlan`/`PGPLAN_*`/`pgplan`.

```sh
python3 -m unittest discover -s auto_test/postgres_replay -p 'test_*.py' -v
bash -n auto_test/pgplan/*.sh auto_test/run_all.sh auto_test/configs.sh
```
