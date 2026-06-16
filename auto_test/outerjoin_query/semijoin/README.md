# semijoin/ — Experiment 1 (`experiment_semijoin.sh`) query templates

Parametric templates run against the generated `dim` / `fact` tables (NOT a fixed
DB), swept over selectivity p and the BASELINE / BITMAP / HASH / DUCKDB_SEMI modes.

- `skeleton_join.sql` — the `dim ⟕ fact` plain outer join (the skeleton all modes time)
- `skeleton_semi.sql`  — the EXISTS-rewrite (DuckDB SEMI form); must equal the plain join

The TPC-H end-to-end family (`--tpch`) reuses the queries under `../tpch/`.
