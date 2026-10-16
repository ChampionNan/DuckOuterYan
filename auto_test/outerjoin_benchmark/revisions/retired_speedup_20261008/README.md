# Retired Graph and JOB queries, 20261008

This archive preserves the original SQL bytes and manifest rows for eleven
queries removed from the active benchmark: two Graph queries and nine JOB queries.
The full-precision DuckDB/OuterYan runtime ratio was at most 0.7 in
`experiment_onoff_benchmark_20261007_161108_t32.csv`. All eleven measurements
have both runtimes below one second. Correctness checks were disabled in that
run, so these are timing observations, not new equivalence checks.

The cumulative evidence policy is `../../sources/speedup_screen_20261008.json`.
It records SQL hashes, runtime values, the original result-file checksum and the
scoped inclusive threshold. Raw results and earlier retirement archives remain
unchanged. No TPC-H or TPC-DS queries were retired in this revision.

Default execution scans only the active `benchmark/` directories. Regeneration
reapplies the frozen exact-SQL policy, so copying an archived SQL file back into
the active directory is not a persistent restoration. To restore it deliberately,
update the pinned policy and expected counts, then regenerate the active corpus.
Historical analysis resolves these SQL files through `benchmark_corpus.py`.
