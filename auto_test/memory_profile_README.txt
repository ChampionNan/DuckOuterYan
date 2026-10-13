CPU9 memory experiment (2026-10-13)
=================================

Scope: the 281 valid measured OuterYan-selected SQL identities in the frozen
20261013 paper results. Family counts: SGPB 47, TPC-H 80, TPC-DS 45, JOB 109.
This is a fixed cohort; a new timeout or selection change is reported, not hidden.
The active benchmark still has 720 SQL queries. SQL SHA256 and manifest SHA256
are checked before running; this tool neither regenerates SQL nor builds data.

Protocol
--------
Each engine uses a fresh read-only DuckDB CLI process for each query. In that
same connection, execute the bare SQL once without profiling as warmup, then
once with JSON profiling. Do not compare/materialize/sort the result for
correctness. CLI trash mode consumes results without formatting them.
DuckDB OFF: SET disabled_optimizers='outer_yan'; ON: empty list.
32 threads, 600 seconds for EACH SQL execution, not a shared two-run deadline.
If a warmup times out, that engine's measurement is not attempted. The other
engine is still tested independently. Alternate the engine order across queries.
There is no automatic retry. No optimization profile or extra timing pass.

Databases: tpch_50.duckdb, tpcds_50.duckdb, job_db, graph_db (Bitcoin), and
graph_epinions.duckdb. Use per-query dataset routing in the pinned cohort.
Fail preflight if base cardinalities do not match SF50/the expected graphs.
Never point this experiment at CPU8's SF100 data.

Metrics and limitations
-----------------------
buffer_peak_bytes: maximum buffer pool memory observed at operator-end callbacks
for the measured query. This is shared database-buffer memory, not total process
memory or exclusive operator allocation. Warm cache pages remain included.

round1/round2: SJ_BUILD and SJ_PROBE of the corresponding round, including replay.
round3: the same physical join-operator categories used by phase_profile.sh.
other: all remaining physical operators, including scan, projection, filter,
aggregation and result handling. Operator categories are NOT disjoint wall-clock
intervals: pipelines overlap and previous rounds' live data can persist.

For each category, take MAX of buffer observations over its operators and workers.
Do NOT sum operator/round peaks or normalize them to percentages. Missing round
operators give null, not a fabricated zero measurement. Boundary sampling can
miss transient allocations (including asynchronous finalization work). It does
not measure all malloc allocations or establish memory ownership by round.

measured_rss_sampled_peak_bytes: Linux /proc process resident memory, sampled
every 50 ms while the measured execution runs. Excludes the warmup execution,
but retains its warm cache. Short-lived peaks may be missed; zero samples means
null/unavailable. RSS is reported for the whole process only, never by round.

spill_peak_bytes: temporary disk usage observed by the profiler, NOT RAM.
profiled_wall_s: diagnostic profiled runtime, NOT a replacement for the existing
median of five unprofiled runs. All original performance results stay unchanged.

The profiler patch retains existing per-operator memory observations and resets
query-global sampled peaks between queries. It does not change cost models,
plan selection, reduction schedules, or aggregation semantics.

Commands
--------
python3 -m unittest discover -s auto_test -p 'test_memory_profile.py'
cmake --build build/release --target duckdb unittest -j 8
build/release/test/unittest '[memory_profile]'
python3 auto_test/memory_profile.py validate
bash auto_test/run_memory_profile.sh --run

The shell script does NOT compile or rebuild databases. Compile first after pull.
Python 3.7+ is supported; on CPU9 set PYTHON_BIN=/usr/local/bin/python3 if needed.

Output: auto_test/results/memory_benchmark_YYYYMMDD_HHMMSS_t32/
  cohort.json: exact SQL identities and reference dataset routing
  run.json: executable hash, git revision, host, database checks, measurement rules
  queries.jsonl: one durable complete pair per query, plus all operator observations
  summary.json: group medians/maxima in MiB, valid-pair counts and failure counts
  profiles/: raw JSON, SQL, decision traces, stage/error logs for every engine
Console log: the same path with .run.log suffix, updated live.

Summary comparisons require both engines to finish and the ON execution to
select OuterYan. Either-engine timeouts/errors and changed selections are
excluded from the paired summary, but retained in the journal and status counts.
Other median/peak summaries are across queries, never sums across queries.
