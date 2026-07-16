# `auto_test/` — OuterYan correctness and performance suite

This directory contains the operational test harness for the OuterYan optimizer.
Use a release build for performance runs. A debug build is useful for assertions,
but its timings are only directional.

The script implementations are authoritative. The option and workflow summaries
below mirror the current versions; `experiment_onoff.sh --help` prints its CLI
synopsis.

## Files

| Path | Purpose |
|---|---|
| `configs.sh` | Defaults shared by `build_db.sh` and `experiment_onoff.sh` |
| `run_all.sh` | Release build, database preparation, then the full experiment |
| `build_db.sh` | Build or reuse graph, TPC-H, TPC-DS, and JOB databases |
| `gen_queries.py` | Generate and validate the SQL corpus |
| `experiment_onoff.sh` | ON/OFF equivalence, plan decision, profiling, and timing |
| `representative_queries.txt` | Ordered P0/P1 cross-family validation manifest |
| `trace_outer_yan.sh` | Write the optimizer-stage trace for one query |
| `outerjoin_query/` | SQL corpus, divided into `graph`, `tpch`, `tpcds`, and `job` |
| `results/` | Generated text, CSV, profile, and trace output |

`trace_outer_yan.sh` has its own command-line/environment defaults and does not
source `configs.sh`.

## Current configuration

Environment variables override `configs.sh`; experiment CLI options override the
corresponding environment values.

| Variable | Current source default | Meaning |
|---|---:|---|
| `DUCKDB_BIN` | `build/release/duckdb` | Release CLI, with debug fallback if release is absent |
| `GRAPH_DATASET` | `bitcoin` | SNAP source used when `graph_db` is built |
| `TPCH_SF` | `100` | TPC-H scale used when `tpch_db` is built |
| `TPCDS_SF` | `100` | TPC-DS scale used when `tpcds_db` is built |
| `OY_THREADS` | `48` | Multi-thread timing and equivalence-check threads |
| `OY_TIMEOUT_SECS` | `600` | Per-query timeout; `0` disables it |
| `OY_RUNS` | `5` | Timed executions after one warm-up |
| `OY_TIMEOUT_RETRY_MULT` | `2` | Timeout multiplier for one retry; `1` disables retry |
| `OY_CAPTURE_PLANS` | `0` | Save OFF/ON EXPLAIN, optimizer trace, and cost-step artifacts |
| `OY_CORPUS` | `auto_test/outerjoin_query` | Corpus root |

Always inspect `configs.sh` before a server run because these experiment defaults
are intentionally adjusted for the current machine.

## Build

For all four families, build a release CLI with the TPC-H and TPC-DS generators:

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
```

`build_db.sh` can also detect missing `dbgen`/`dsdgen` support and rebuild the
release binary when needed.

## Databases

```text
bash auto_test/build_db.sh [graph|tpch|tpcds|job|all ...]
```

| Database | Source |
|---|---|
| `graph_db` | One SNAP edge list copied into R1..R10, plus R/S/T/K views |
| `tpch_db` | `CALL dbgen(sf=TPCH_SF)` |
| `tpcds_db` | `CALL dsdgen(sf=TPCDS_SF)` |
| `job_db` | 21 JOB/IMDb Parquet files cached under `job_data/`, then loaded locally |

Existing database files are reused. Merely changing `GRAPH_DATASET`, `TPCH_SF`,
or `TPCDS_SF` does not change an existing database. Use `FORCE=1` deliberately:

```bash
# Small TPC databases
FORCE=1 TPCH_SF=1 bash auto_test/build_db.sh tpch
FORCE=1 TPCDS_SF=1 bash auto_test/build_db.sh tpcds

# Replace graph_db with the wiki graph
FORCE=1 GRAPH_DATASET=wiki bash auto_test/build_db.sh graph
```

JOB has no scale factor. Missing Parquet files are downloaded with `curl`; cached
files are reused. `FORCE=1` rebuilds `job_db` from that cache rather than forcing a
second download.

When `experiment_onoff.sh --only graph` is used, `graph_db` is reused by default.
Set `OY_FORCE_GRAPH_REBUILD=1` only when replacing it is intentional.

## Query corpus

The checked-in corpus currently contains graph, TPC-H, TPC-DS, and JOB outer-join
queries. Labels are SQL basenames without `.sql`; `--pattern` and `--exclude`
match the entire label using shell-glob syntax.

```bash
python3 auto_test/gen_queries.py graph
python3 auto_test/gen_queries.py bench       # tpch + tpcds + job
python3 auto_test/gen_queries.py validate
python3 auto_test/gen_queries.py all
```

Generation is deterministic. Validation executes `EXPLAIN` against the prepared
databases and may remove generated queries that do not bind.

## Experiment pipeline

For every selected query, `experiment_onoff.sh` performs these operations:

1. Execute the bare query with OuterYan OFF and ON, sort the emitted CSV files
   outside DuckDB, and compare the result multisets. A mismatch, error, or
   timeout is not timed. No SQL wrapper changes the optimized plan.
2. Run a traced `EXPLAIN` in a fresh process and read one `[OY_DECISION]` record.
3. If OuterYan was selected, run one kernel-classification execution and record
   bitmap/hash filter counts.
4. Run one profiled OuterYan-ON execution at `threads=1` and categorize operator
   elapsed time as round-1 semi-join, round-2 semi-join, and real joins.
5. Time OuterYan OFF and ON at `threads=1` and `threads=$OY_THREADS`. Each batch
   has one warm-up followed by `--runs N` timed executions; the median excludes
   the warm-up.
6. Retry timed-out queries once with `OY_TIMEOUT_RETRY_MULT` times the timeout.

The phase values are sums of categorized single-thread operator times. They are
not complete phase wall times and need not add up to the measured query time.

### Plan decision and cost gate

For an applicable query, OuterYan constructs its DP/OJT candidate and DuckDB's
normal outer-join-simplified, join-ordered baseline from the same input plan.
Grouping comparison uses stable base-table identities and ignores join type,
child orientation, and inserted semi-join wrappers.

A same-grouping candidate always selects DuckDB. For a changed grouping, the
source-level gate computes:

```text
semijoin_raw_cost = round1_build + round1_probe + round2_build + round2_probe
weighted_semijoin_cost = SEMIJOIN_COST_RATIO * semijoin_raw_cost
candidate_total = candidate_join_cost + weighted_semijoin_cost
baseline_threshold = MAX_CANDIDATE_TO_BASELINE_RATIO * baseline_cost

select OuterYan iff candidate_total <= baseline_threshold
```

The trace and CSV report two separate comparisons: `raw_cost_winner` compares
`candidate_total` directly with `baseline_cost`, while `gate_result` compares
`candidate_total` with `baseline_threshold`. `selected_plan` is the plan that
is actually returned and can differ because of same-grouping or proven-empty
policy decisions.

The policy knobs are `constexpr` members of `OuterYanOptimizer` in
`src/include/duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp`; they
are not environment variables or SQL settings. The current workspace has the
gate enabled, a semi-join ratio of `0.35`, and a baseline limit of `1.0`. Rebuild
the CLI after changing them.

Decision reasons written to the trace and result files include:

| Reason | Meaning |
|---|---|
| `INAPPLICABLE` | OuterYan applicability check failed |
| `DUCKDB_PLAN` | Candidate has the same grouping as DuckDB; use DuckDB |
| `DUCKDB_PROVEN_EMPTY` | DuckDB's proof copy eliminates all real join work; use DuckDB without SJs |
| `ALWAYS_OUTERYAN` | Grouping changed and the source-level cost gate is disabled |
| `COST_OUTERYAN_BETTER` | Changed candidate passed the configured threshold |
| `COST_DUCKDB_BETTER` | Changed candidate exceeded the configured threshold |
| `COST_UNAVAILABLE` | A finite comparison could not be produced |
| `OUTERYAN_FAILED` | OuterYan did not produce a complete candidate |

AggregatePushdownOuter is applied to either winner using metadata corresponding
to that winner's join shape. Semi-join operators are inserted only when the
OuterYan candidate is selected.

### Command-line options

```text
bash auto_test/experiment_onoff.sh [options]
  -b, --bin PATH      DuckDB CLI
  -n, --runs N        timed executions per configuration
  -t, --timeout S     per-query timeout
      --only FAMILY   select|agg|pred|graph|tpch|tpcds|job|bench|all
      --pattern GLOB  include matching labels
      --exclude GLOB  exclude matching labels; separate globs with |
      --limit N       global query cap; 0 means unlimited
      --query-list FILE  ordered corpus-relative SQL paths; requires --only all
      --capture-plans save OFF/ON EXPLAIN, trace, and detailed cost files
  -o, --out FILE      exact text output path
```

`select`, `agg`, and `pred` currently alias the graph family; they do not filter
the graph filenames further. `bench` expands to TPC-H, TPC-DS, and JOB. `--limit`
is global and follows that family order.

### Examples

```bash
# Four small graph queries, single-thread smoke run
GRAPH_DATASET=bitcoin OY_THREADS=1 OY_TIMEOUT_RETRY_MULT=1 \
bash auto_test/experiment_onoff.sh \
  --only graph --pattern '*_N3_*_s0[15]' --limit 4 --runs 1 --timeout 60

# Two three-relation aggregate queries from each benchmark family
TPCH_SF=1 TPCDS_SF=1 OY_THREADS=4 \
bash auto_test/experiment_onoff.sh \
  --only bench --pattern '*_agg[01]' --limit 6 --runs 1

# Full TPC-H family
bash auto_test/experiment_onoff.sh --only tpch

# Skip JOB bushy-7 labels
bash auto_test/experiment_onoff.sh --only bench --exclude '*jb_bushy7*'

# P0/P1 representative run using existing databases
SKIP_DATA=1 OY_THREADS=48 OY_RUNS=3 bash auto_test/run_all.sh \
  --only all --query-list auto_test/representative_queries.txt --capture-plans
```

The release build enables TPCH and TPCDS but does not build HTTPFS.
None of the four benchmark builders requires HTTPFS: network downloads use the
`curl` executable and JOB reads cached local Parquet. Build HTTPFS separately
only on hosts with compatible libcurl development headers.

The scale variables in the second example describe the prepared databases in
the report header; rebuild the databases first if they are not already SF1.

## Output

Without `--out`, one start timestamp is used for the result group:

```text
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS.txt
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS.csv
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS.attempts.csv
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS.plans/
```

With `--out path/name.txt`, the text path is exact and the CSV is
`path/name.csv`. The canonical CSV contains exactly one effective row per query
after retries. The attempts CSV retains both main and retry rows.

The live stderr line contains `reorder`, `selected`, `reason`, `raw`, and
`gate`, followed by an indented calculation:

```text
cost: OuterYan=<join> + <sj_ratio>*<sj_raw> = <total> vs DuckDB=<baseline> ...
```

The same record prints all join-output and SJ materialize/build/replay/lookup/
emit weights. With plan capture enabled, every query has DuckDB-OFF and enabled
EXPLAIN files, a full trace, and per-join/per-SJ cost records.

The text table includes:

| Field | Meaning |
|---|---|
| `outer` | `outer_reordered`: candidate grouping differs from DuckDB |
| `gate` | Numeric gate was applied |
| `useOY` | OuterYan candidate was actually selected and executed |
| `decision` | Reason token from the table above |
| `kernel` | `bitmap`, `hash`, `mixed`, or `-` |
| `correct` / `note` | Equivalence result and failure category |
| `T1:*` / `TM:*` | OFF, ON, and `OFF/ON` speed-up at one/many threads |
| `R1SJ-T1`, `R2SJ-T1`, `JOIN-T1` | Categorized single-thread operator elapsed seconds |

Each correct query is followed by raw cost components and an expanded gate:

```text
gate formula: candidate_join + semijoin_ratio * semijoin_raw <= baseline_ratio * baseline
gate values:  <join> + <sj-ratio> * <raw-sj> <= <baseline-ratio> * <baseline>
gate result:  <candidate-total> <= <threshold> => PASS|FAIL -> <decision>
```

For same-grouping, inapplicable, unavailable, or forced-policy cases, the report
states that the numeric gate was skipped and prints the decision reason.

The CSV exports the same decision, cost, kernel, correctness, timing, and phase
fields in machine-readable form. Retry rows use `pass=retry`; when both main and
retry rows exist, take the last row for that query. The final text summary already
uses the post-retry state and groups speed-ups separately by `outer_reordered` and
`outer_yan_selected`.

## Optimizer trace

`DUCKDB_OYTRACE=/path/to/file` enables the file-based optimizer trace in release
and debug builds. It records the SQL, logical input, OT/OJT stages, semi-join
pairs, DuckDB baseline, cost comparison, final `[OY_DECISION]`, and selected plan.
Tracing adds planning and file-I/O overhead and should not wrap a timed execution.
The experiment harness avoids that by collecting its decision in a separate
traced `EXPLAIN` process.

`trace_outer_yan.sh` defaults to the debug CLI, but `-b` can select release:

```bash
# Trace a corpus file with release
bash auto_test/trace_outer_yan.sh \
  -b build/release/duckdb --db tpch_db \
  -f auto_test/outerjoin_query/tpch/oy_th_th_agg0.sql

# Trace inline SQL
bash auto_test/trace_outer_yan.sh \
  -b build/release/duckdb --db graph_db \
  -q "SELECT * FROM R1 LEFT JOIN R2 ON R1.dst=R2.src;"

# Trace the five historical R/S/T/K cases
bash auto_test/trace_outer_yan.sh -b build/release/duckdb --db graph_db fails
```

The graph builder creates R/S/T/K views, so no manual view setup is required.

## Semi-join kernel controls

| Control | Current default | Effect |
|---|---:|---|
| `outer_yan_bitmap_max_bytes` | 16 GiB per filter | Bitmap budget; `0` forces hash |
| `outer_yan_hash_fn` | `duckdb` | Hash implementation; alternative is `murmur` |
| `outer_yan_stats_prefilter` | `false` | Use base min/max statistics to skip unsuitable bitmap attempts |
| `DUCKDB_SJ_KERNEL_TRACE` | unset | Emit finalized bitmap/hash kernel records |

Set session controls with DuckDB variables, for example:

```sql
SET VARIABLE outer_yan_bitmap_max_bytes = 0;
SET VARIABLE outer_yan_hash_fn = 'murmur';
SET VARIABLE outer_yan_stats_prefilter = true;
```

Disable the cohesive optimizer with:

```sql
SET disabled_optimizers TO 'outer_yan';
```

## One-command and manual workflows

```bash
# Build release, prepare/reuse every database, run every family
bash auto_test/run_all.sh

# Reuse an existing release binary and databases
SKIP_BUILD=1 SKIP_DATA=1 bash auto_test/run_all.sh --only tpch
```

Manual equivalent:

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
bash auto_test/build_db.sh all
bash auto_test/experiment_onoff.sh
```

`run_all.sh` and `build_db.sh` reuse existing database files. If a requested
scale or graph differs from the database already on disk, rebuild that database
explicitly with `FORCE=1` before running the experiment.
