# PGPlan

This is the canonical user-facing entry point for the PostgreSQL logical-tree
baseline. A normal run needs no PostgreSQL or Docker environment setting:

```sh
bash auto_test/run_all.sh
```

The default source provider installs and starts pinned PostgreSQL 16.2 under
the repository when it is missing, prepares minimal plan-selection data, then
compares native DuckDB, PGPlan, and normal OuterYan across all 206 queries in
`auto_test/outerjoin_query`. Docker is an optional provider selected with
`PGPLAN_SETUP=docker`. Both managed providers generate and reuse a private
mode-`0600` password file unless a password is explicitly provided; a legacy
container with a different credential is rejected with recovery instructions.

Manual PGPlan commands are:

```sh
bash auto_test/pgplan/setup_pg.sh
auto_test/pgplan/make_plan.sh --query QUERY.sql --out QUERY.pg.json
auto_test/pgplan/prepare_correctness_db.sh --help
auto_test/pgplan/experiment.sh --help
auto_test/pgplan/prepare_sampled_pg.sh --help
auto_test/pgplan/corpus_experiment.sh --help
```

The workflow keeps three data roles separate:

1. PostgreSQL plan selection uses exact TPC-H SF0.01 or isolated graph,
   TPC-DS, and JOB schemas sampled at no more than 1000 rows per table by
   default. PostgreSQL only runs plain `EXPLAIN`; it never executes the result
   query.
2. Exact Native/PGPlan/OuterYan result comparison uses a bounded small DuckDB
   database: deterministic graph rowid-prefix 500, TPC-H `dbgen` SF0.01, TPC-DS
   `dsdgen` SF0.01, or JOB rowid-prefix 1000. TPC-DS and JOB can include
   bounded target-rowid witnesses captured from the current target execution.
   Prefixes and generator bases are deterministic, but witness enrichment is
   not a claim of byte-identical fixtures across engines or runs, and not every
   query result is claimed to be nonempty. Row prefixes, the maximum allowed query-result
   cardinality, and the validation timeout are configurable through
   `PGPLAN_CORRECTNESS_GRAPH_ROWS`, `PGPLAN_CORRECTNESS_JOB_ROWS`,
   `PGPLAN_CORRECTNESS_MAX_RESULT_ROWS`, and
   `PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS`.
3. The configured target DuckDB database supplies EXPLAIN, PGPlan semantic
   verification, and output-discarding timing.

Corpus runs SHA-256 fingerprint the exact bounded correctness database and its
builder manifest once per family, then copy those provenance records into every
query result directory.

For a manual query, pass both databases explicitly:

```sh
auto_test/pgplan/experiment.sh \
  --execution-db /absolute/path/to/target.duckdb \
  --correctness-db /absolute/path/to/small-correctness.duckdb \
  --duckdb-bin /absolute/path/to/duckdb \
  --query /absolute/path/to/query.sql \
  --plan /absolute/path/to/query.pg.json \
  --out /absolute/path/to/results
```

Thus a successful run establishes complete three-way multiset equality on the
small database and PGPlan tree adherence plus performance on target data. It
does not establish target-scale result equality or execute PostgreSQL's
physical plan.

Plan capture always uses plain PostgreSQL `EXPLAIN`, never `EXPLAIN ANALYZE`.
Its default 60-second optimizer limit is controlled by
`PGPLAN_CAPTURE_TIMEOUT_SECS`/`--capture-timeout`. DuckDB's separate
three-way execution limit is controlled by `PGPLAN_TIMEOUT_SECS`/`--timeout`.
That limit also covers complete-result CSV framing, sorting, comparison, and
hashing. Either timeout records that query as `SKIP` and continues with the
corpus; non-timeout errors remain `FAIL`.

The [complete PGPlan guide](../postgres_replay/README.md) documents setup,
artifacts, semantic scope, strict validation, and result files. Its directory
name is retained for internal compatibility; commands, settings, diagnostics,
modes, and generated result names use `PGPlan`/`PGPLAN_*`/`pgplan`.
