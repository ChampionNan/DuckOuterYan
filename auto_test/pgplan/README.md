# PGPlan

This is the canonical user-facing entry point for the PostgreSQL logical-tree
baseline. PGPlan is opt-in; the source provider needs no Docker setting:

```sh
RUN_PGPLAN=1 bash auto_test/run_all.sh
```

The default source provider installs and starts pinned PostgreSQL 16.2 under
the repository when it is missing, prepares minimal plan-selection data, then
compares native DuckDB, PGPlan, and normal OuterYan across all 185 active queries in
`auto_test/outerjoin_query`. Docker is an optional provider selected with
`PGPLAN_SETUP=docker`. Both managed providers generate and reuse a private
mode-`0600` password file unless a password is explicitly provided; a legacy
container with a different credential is rejected with recovery instructions.
The tooling supports Python 3.7+ using only the standard library. Set
`PYTHON_BIN=/absolute/path/to/a/repo-local/python3` to avoid the system Python;
no separate Python installation is required for a normal run.

PGPlan artifacts persist by default under `auto_test/pgplan/plans`. Before
starting PostgreSQL, the corpus runner checks that location for every selected
query. Each JSON artifact has an artifact-bound sample-identity sidecar. A
cache entry is accepted only when its canonical query hash, artifact bytes,
PostgreSQL 16.2 provenance/settings, family schema/data label, exact bounded
planning-sample fingerprint, statistics epoch, and typed binary tree all
validate. A single miss recaptures that selected family coherently under one
new `ANALYZE` epoch; fully cached families do not start PostgreSQL. A missing,
malformed, or stale entry is recaptured and replaced atomically, and every
result directory still receives its own immutable copy. Override the location
with `PGPLAN_PLAN_CACHE` or `--plan-cache`. Delete one cached JSON file (or
choose a new cache directory) to force that family's coherent recapture.

Correctness comparison mode is independent of the cached plan and performance
work:

```sh
# PGPlan mode: (a) Original == PGPlan and (b) Original == OuterYan
RUN_PGPLAN=1 bash auto_test/run_all.sh

# skip1: run only comparison (a)
RUN_PGPLAN=1 bash auto_test/run_all.sh --skip1

# skip2: do not rerun correctness; still run EXPLAIN, PGPlan verification,
# and Original/PGPlan/OuterYan TM performance
RUN_PGPLAN=1 bash auto_test/run_all.sh --performance-only
```

`--skip2`, `--performance_only`, and the accepted compatibility misspelling
`--performace_only` are aliases for `--performance-only`. This manual mode
records correctness as `NOT_RUN`; it does not claim to validate an earlier
result. Use `--reuse-from` when the earlier target-data comparison must be
cryptographically validated before performance is rerun.

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

For a later performance-only rerun of the same corpus inputs, reuse the sealed
target correctness receipts and the retained PGPlan artifacts:

```sh
RUN_PGPLAN=1 bash auto_test/run_all.sh \
  --reuse-from /absolute/path/to/prior/pgplan_corpus_YYYYMMDD_HHMMSS
```

This one option automatically preserves the existing binary, target databases,
and query files (Steps 1--3 are skipped), and skips PostgreSQL setup, sampled
schema preparation, and plan capture. Native, PGPlan, and OuterYan EXPLAIN,
semantic verification and TM run normally in a new self-contained result
directory. The prior receipt must be a sealed fresh target-mode comparison and
must match the exact query, PGPlan artifact, DuckDB binary/version, and target
database hashes. A missing/mismatched receipt or plan, an escaping prior path,
or a non-empty target `.wal` fails that query without falling back; later
queries continue. Use `PGPLAN_CORRECTNESS_MODE=reuse` with
`PGPLAN_CORRECTNESS_FROM` only when correctness should be reused but a fresh
PostgreSQL plan should still be captured.

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

Thus a default successful run establishes both target-data equalities
(Original=PGPlan and Original=OuterYan), PGPlan tree adherence, and performance.
A bounded-mode PASS is scoped to its recorded small database. Neither mode
executes PostgreSQL's physical plan.

A reuse-mode PASS does not perform or claim a second result comparison. It
cryptographically cites the matching prior target-mode equality receipt, then
reruns all three current plan checks and timing configurations. The new run
copies the PGPlan artifact and receipt provenance instead of depending on the
prior directory at report time.

Plan capture always uses plain PostgreSQL `EXPLAIN`, never `EXPLAIN ANALYZE`.
Its default 300-second optimizer limit is controlled by
`PGPLAN_CAPTURE_TIMEOUT_SECS`/`--capture-timeout`. DuckDB's separate execution
limit is controlled by `PGPLAN_TIMEOUT_SECS`/`--timeout`.
That limit also covers complete-result CSV framing, sorting, comparison, and
hashing. Either timeout records that query as `SKIP` and continues with the
corpus, but the corpus exits nonzero because the query is incomplete;
non-timeout errors remain `FAIL`.

The corpus stage is the complete Original/PGPlan/OuterYan performance run; it
is not a PG-only execution pass. Per-query medians are stored in
`runs/<family>/<query>/timing/summary.tsv`. The result root contains
`comparison.tsv`/`comparison.csv` for all selected queries, a human-readable
`comparison.log`, `summary.tsv` for overall and per-family aggregate speedups,
and `failures.tsv` for incomplete queries. Every normal PASS/FAIL/SKIP is
streamed immediately as a legacy-style, separator-delimited block and retained
in `comparison.log`, which contains the same ordered records and values as the
machine-readable comparison files.

The comparison CSV/TSV preserves the complete `experiment_onoff.sh` CSV header
as its leading columns, in exactly the original order. PGPlan verification,
TM, correctness mode, and provenance columns follow that prefix, with
`pgplan` in every appended field name. Raw plan signatures are retained only
in trace artifacts, not in the human log or CSV.

The appended correctness fields distinguish `FRESH`, `PARTIAL`, `NOT_RUN`, and
`REUSED` work. In particular, `pgplan_correctness_origin` and
`pgplan_correctness_comparison_executed` state whether this result directory
performed a comparison. Reused rows retain their source and receipt SHA-256
values in `pgplan_correctness_*` columns. Older results remain readable with
empty fields instead of guessed values.

For every completed performance run, the CSV's `tm_off` / `tm_on` columns
retain their Original/OuterYan meanings. Appended `tm_pgplan` adds PGPlan.
Legacy Original/PGPlan speedup
fields remain for compatibility, and PGPlan/OuterYan fields provide the direct
comparison. The human line orders each suite as Original, PGPlan, OuterYan and
prints exactly `Original/OuterYan` and `PGPlan/OuterYan`. TM uses one warm-up
plus the configured odd measured-run count. There is no single-thread batch
or phase profiling. New reports omit `t1_*` and `profile_*` columns; historical
`t1_*` values are appended only when re-summarizing actual old T1 artifacts.
Kernel tracing is not collected; its CSV fields remain unavailable. The
`rows` column refers to the complete target result by default. Timing
uses `.mode trash`, which executes and fully materializes the bare query
while excluding CLI result serialization and filesystem output from the real
DuckDB CLI wall-clock measurement. Only `PASS` rows have timing values.

`run_all.sh` defaults to sequential 16- and 32-thread configurations, saved in
separate `_t16` / `_t32` directories. Use `--threads 16` for just one. When
reusing correctness, select the thread count matching the source receipt;
receipts are not reusable across thread counts.

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
