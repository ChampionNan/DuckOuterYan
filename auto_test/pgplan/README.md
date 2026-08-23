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
The tooling supports Python 3.7+ using only the standard library. Set
`PYTHON_BIN=/absolute/path/to/a/repo-local/python3` to avoid the system Python;
no separate Python installation is required for a normal run.

Manual PGPlan commands are:

```sh
bash auto_test/pgplan/setup_pg.sh
auto_test/pgplan/make_plan.sh --query QUERY.sql --out QUERY.pg.json
auto_test/pgplan/prepare_correctness_db.sh --help
auto_test/pgplan/experiment.sh --help
auto_test/pgplan/prepare_sampled_pg.sh --help
auto_test/pgplan/corpus_experiment.sh --help
```

The workflow separates PostgreSQL plan-selection data from DuckDB target data:

1. PostgreSQL plan selection uses exact TPC-H SF0.01 or isolated graph,
   TPC-DS, and JOB schemas sampled at no more than 1000 rows per table by
   default. PostgreSQL only runs plain `EXPLAIN`; it never executes the result
   query.
2. The configured target DuckDB database supplies complete Native/PGPlan/
   OuterYan multiset correctness, EXPLAIN, PGPlan semantic verification, and
   timing by default.

Set `PGPLAN_CORRECTNESS_MODE=bounded` explicitly for a quicker diagnostic. It
uses deterministic graph rowid-prefix 500, TPC-H `dbgen` SF0.01, TPC-DS
`dsdgen` SF0.01, or JOB rowid-prefix 1000. TPC-DS and JOB can include bounded
target-rowid witnesses. Its row prefixes, result cap, and validation timeout
use `PGPLAN_CORRECTNESS_GRAPH_ROWS`, `PGPLAN_CORRECTNESS_JOB_ROWS`,
`PGPLAN_CORRECTNESS_MAX_RESULT_ROWS`, and
`PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS`.

Bounded corpus runs SHA-256 fingerprint their correctness database and builder
manifest once per family, then copy those provenance records into every query
result directory.

For a default manual query, pass the target database once; correctness defaults
to that same file:

```sh
auto_test/pgplan/experiment.sh \
  --execution-db /absolute/path/to/target.duckdb \
  --duckdb-bin /absolute/path/to/duckdb \
  --query /absolute/path/to/query.sql \
  --plan /absolute/path/to/query.pg.json \
  --out /absolute/path/to/results
```

Pass `--correctness-db /absolute/path/to/small-correctness.duckdb` only when an
explicit bounded/manual correctness scope is intended.

Thus a default successful run establishes complete three-way target-data
multiset equality, PGPlan tree adherence, and performance. A bounded-mode PASS
is scoped to its recorded small database. Neither executes PostgreSQL's
physical plan.

Plan capture always uses plain PostgreSQL `EXPLAIN`, never `EXPLAIN ANALYZE`.
Its default 300-second optimizer limit is controlled by
`PGPLAN_CAPTURE_TIMEOUT_SECS`/`--capture-timeout`. DuckDB's separate
three-way execution limit is controlled by `PGPLAN_TIMEOUT_SECS`/`--timeout`.
That limit also covers complete-result CSV framing, sorting, comparison, and
hashing. Either timeout records that query as `SKIP` and continues with the
corpus, but the corpus exits nonzero because the query is incomplete;
non-timeout errors remain `FAIL`.

The corpus stage is the complete three-way benchmark; it is not a PG-only
execution pass. Per-query medians are stored in
`runs/<family>/<query>/timing/summary.tsv`. The result root contains
`comparison.tsv`/`comparison.csv` for all selected queries, a human-readable
`comparison.log`, `summary.tsv` for overall and per-family aggregate speedups,
and `failures.tsv` for incomplete queries. Every normal PASS/FAIL/SKIP is
streamed immediately as a legacy-style, separator-delimited block and retained
in `comparison.log`, which contains the same ordered records and values as the
machine-readable comparison files.

The comparison CSV/TSV preserves the complete `experiment_onoff.sh` CSV header
as its leading columns, in exactly the original order. PGPlan artifact,
verification, TM/T1, and pairwise-speedup columns follow that prefix; corpus
status and provenance fields use a `three_way_` prefix. The text log likewise
keeps the original separator plus two-line query block and appends PGPlan
timing and verification information.

For every `PASS`, the original `TM:off/on` and `T1:off/on` columns remain the
Native/OuterYan comparison. Appended `tm_pgplan` and `t1_pgplan` columns add the
third target-data median and both PGPlan pairwise speedups. Ratios are baseline
time divided by candidate time, so a value above one favors the named
candidate. The three-way corpus runs independent timing batches for all three
configurations: TM uses one warm-up plus the configured odd measured-run count,
while T1 uses one warm-up plus exactly one measured run. It does not yet
collect the legacy phase profile and semi-join kernel trace, so those remain
explicitly not collected. The original
`rows` column refers to the complete target result by default. Both timing
suites use `.mode trash`, which executes and fully materializes the bare query
while excluding CLI result serialization and filesystem output from the real
DuckDB CLI wall-clock measurement. Only `PASS` rows have timing values.

To build or rebuild those reports from an existing run without repeating
PostgreSQL capture, correctness checks, or timing:

```sh
bash auto_test/pgplan/summarize_corpus.sh \
  --result-dir /absolute/path/to/pgplan_corpus_YYYYMMDD_HHMMSS
```

This also regenerates `comparison.log`; use `less` or `cat` to display it. No
PostgreSQL capture, correctness execution, or timing execution is repeated.

The [complete PGPlan guide](../postgres_replay/README.md) documents setup,
artifacts, semantic scope, strict validation, and result files. Its directory
name is retained for internal compatibility; commands, settings, diagnostics,
modes, and generated result names use `PGPlan`/`PGPLAN_*`/`pgplan`.
