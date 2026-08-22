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
auto_test/pgplan/experiment.sh --help
auto_test/pgplan/prepare_sampled_pg.sh --help
auto_test/pgplan/corpus_experiment.sh --help
```

TPC-H plan selection uses exact SF0.01. Graph, TPC-DS, and JOB use isolated
schemas sampled from their DuckDB databases, with at most 1000 rows per table
by default. Those datasets select PostgreSQL's typed logical join tree only;
all three configurations execute on the target DuckDB databases.

The [complete PGPlan guide](../postgres_replay/README.md) documents setup,
artifacts, semantic scope, strict validation, and result files. Its directory
name is retained for internal compatibility; commands, settings, diagnostics,
modes, and generated result names use `PGPlan`/`PGPLAN_*`/`pgplan`.
