# PostgreSQL outer-join witnesses

`witnesses.sql` is a diagnostic input, separate from the main benchmark.
The historical trace report is a local ignored artifact.

Build PostgreSQL 16.2 with the instrumentation patch in
`../pg_plan_comparison/patches/postgresql-16.2-ojtrace.patch` and set
`PG_OJ_TRACE=1` in the environment before starting that server. Execute
`witnesses.sql` in one psql session against a disposable test database.
It creates temporary tables and inspects outer-join plans.

Server logs and query output must go under ignored `auto_test/results/`
or outside this checkout. See `../pg_plan_comparison/README.md` for the
build and comparison runners. No captured trace is distributed here.
