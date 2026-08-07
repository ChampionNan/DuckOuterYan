# Yannakakis<sup>+</sup>

This repository is a DuckDB research fork for optimizing acyclic queries with
inner and outer joins. Its `OuterYan` path combines join reordering, two-round
semi-join reduction, and bitmap/hash semi-join kernels. Aggregate-pushdown code
is retained for research, but the current policy keeps aggregate and DISTINCT
queries on DuckDB's normal optimizer path.

## Build

Building requires CMake, Python 3, Ninja, and a C++17 compiler. Use a release
build for performance measurements:

```bash
GEN=ninja make release
```

TPC-H and TPC-DS database generation requires their extensions. You can include
them up front, or let `auto_test/build_db.sh` rebuild the release binary if they
are missing:

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
```

The resulting CLI is `build/release/duckdb`. A debug build is available with
`GEN=ninja make debug`, but its timings are only directional.

## One-command build and test

From the repository root, the complete OuterYan workflow is:

```bash
bash auto_test/run_all.sh
```

This command:

1. builds the release DuckDB CLI containing the current OuterYan code;
2. builds or reuses the graph, TPC-H, TPC-DS, and JOB databases according to
   `auto_test/configs.sh`;
3. runs every query under `auto_test/outerjoin_query/{graph,tpch,tpcds,job}`; and
4. writes timestamped reports to:

```text
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS.txt
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS.csv
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS.attempts.csv
```

Existing databases are reused. If dataset or scale settings changed and every
database should be rebuilt, run:

```bash
FORCE=1 bash auto_test/run_all.sh
```

## OuterYan plan selection

For an applicable query, `OuterYanOptimizer` builds two alternatives from the
same logical input:

1. DuckDB's normal outer-join-simplified and join-ordered plan.
2. The OuterYan DP/OJT plan with its proposed semi-join reductions.

The optimizer compares their base-relation join groupings using stable table
identities. Join kind, left/right child orientation, and semi-join wrappers do
not affect this comparison. A candidate with the same grouping uses DuckDB's
plan, avoiding semi-join overhead without a join-order benefit.

For a different grouping, the default source-level cost gate evaluates:

```text
candidate_total = candidate_join_cost
                + SEMIJOIN_COST_RATIO * semijoin_raw_cost

candidate_total <= MAX_CANDIDATE_TO_BASELINE_RATIO * baseline_cost
```

The current build uses `GATED`. Its cost model uses
`SEMIJOIN_COST_RATIO=0.35` and
`MAX_CANDIDATE_TO_BASELINE_RATIO=1.0`, so OuterYan is selected only when its
estimated total cost does not exceed DuckDB's baseline cost. Cost formula V3
also closes two lower-tail false positives without changing that global
threshold:

- A fully reduced all-INNER candidate cannot estimate an intermediate result
  below the largest reduced leaf in that subtree.
- When DuckDB had to use its generic table-filter selectivity, both plans are
  re-scored once with the unfiltered base cardinality. The gate must pass the
  worse of the ordinary and conservative candidate/baseline ratios.
- A candidate is rejected when such an uncertain tiny relation is amplified
  by at least `1000x` while both reducer rounds retain at least `99%` of their
  estimated input rows. In that pattern, the filter assumption is driving a
  large reorder without a credible reduction benefit.

Before policy selection, a conservative
proof copy runs DuckDB statistics propagation and empty-result pull-up; if that
removes every real join, DuckDB is selected with `DUCKDB_PROVEN_EMPTY`.

The trace and reports distinguish the raw cost winner, the threshold result,
and the final selected plan. They also print the exact join-output and SJ
materialize/build/replay/lookup/emit coefficients.

The policy constants, including `APPLY_COST_GATE`, live in
[`outer_yan_optimizer.hpp`](src/include/duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp).
They are deliberately build-wide source knobs rather than SQL settings. The
selected OuterYan plan receives semi-join insertion. Aggregate and DISTINCT
queries bypass candidate construction entirely; inapplicable queries and
queries with OuterYan disabled likewise continue through DuckDB's normal
optimizer.

### Force the OuterYan candidate for correctness validation

`FORCE_OUTERYAN` is an optional source-level experiment mode. It bypasses the
cost gate for a changed grouping, but the same-grouping policy can still select
DuckDB. To execute a valid OuterYan candidate even when its grouping matches
DuckDB or its estimated cost is worse, scope the diagnostic override to the
test command:

```bash
DUCKDB_OY_FORCE_CANDIDATE=1 \
bash auto_test/experiment_onoff.sh \
    --only tpcds \
    --pattern 'oy_ds_ds_bushy5b_v0' \
    --runs 3 \
    --capture-plans
```

The OFF execution still disables OuterYan, while every ON subprocess inherits
the diagnostic override. This makes the bare-query equivalence check compare
DuckDB with the actually executed OuterYan candidate. The override applies only
to a complete, applicable, non-aggregate, non-proven-empty candidate; it does
not override safety fallbacks for aggregate/DISTINCT, inapplicable, failed, or
DuckDB-proven-empty plans.

Confirm the result line contains `selected=OUTERYAN`, and confirm its decision
contains:

```text
mode=FORCE_OUTERYAN_DIAGNOSTIC
reason=FORCE_OUTERYAN_DIAGNOSTIC
outer_yan_selected=1
gate=SKIPPED
```

`reorder=0` is valid in this mode: it means only that the real-join grouping is
the same, not that DuckDB executed. Kernel and R1/R2 fields provide additional
evidence that the semi-join plan ran. Keep the variable command-scoped as shown;
without it, normal `GATED`/`FORCE_OUTERYAN` selection is unchanged.

Disable the cohesive OuterYan path for a session with:

```sql
SET disabled_optimizers TO 'outer_yan';
```

## Correctness and performance harness

The scripts and corpus live under [`auto_test/`](auto_test/). See
[`auto_test/README.md`](auto_test/README.md) for the complete command reference,
dataset notes, output schema, and troubleshooting guidance.

Common commands:

```bash
# Build or reuse the graph, TPC-H, TPC-DS, and JOB databases.
bash auto_test/build_db.sh all

# Run the full ON/OFF corpus.
bash auto_test/experiment_onoff.sh

# Start with a small graph correctness/performance sample.
bash auto_test/experiment_onoff.sh \
    --only graph --pattern 'line_N3_*' --limit 3 --runs 1

# Run one exact TPC-H query label.
bash auto_test/experiment_onoff.sh \
    --only tpch --pattern 'oy_th_th_branch5a_v2'

# Force one complete OuterYan candidate, ignoring grouping equality and cost.
DUCKDB_OY_FORCE_CANDIDATE=1 \
bash auto_test/experiment_onoff.sh \
    --only tpcds --pattern 'oy_ds_ds_bushy5b_v0' --capture-plans

# Release build plus P0/P1 representative bare-query validation (3–7 relations).
SKIP_DATA=1 OY_THREADS=48 OY_RUNS=3 bash auto_test/run_all.sh \
    --only all \
    --query-list auto_test/representative_queries.txt \
    --capture-plans
```

`run_all.sh` does not build HTTPFS. The benchmark databases use
local files: graph and JOB downloads use the `curl` executable, and JOB is
loaded from cached Parquet. HTTPFS can be built separately when needed on a
host with compatible libcurl development headers.

`experiment_onoff.sh` first executes the bare query with OuterYan ON and OFF,
then compares the emitted result multisets outside DuckDB. Only equivalent
queries are timed. It measures both `threads=1` and
`threads=$OY_THREADS`, and writes a human-readable `.txt` report plus a matching
`.csv` file under `auto_test/results/` by default.

The external correctness sort uses `<repo>/auto_test/results/tmp` by default.
For the server checkout shown above, that is
`/home/data/bchenba/DuckYanOuter/auto_test/results/tmp`, backed by the `/home`
filesystem with roughly 3.9 TB free. The harness prints the resolved path,
per-run subdirectory, available capacity, and mount point before the first
query. The per-run directory is removed on normal exit and Ctrl+C. Set
`OY_TMPDIR=/path/with/free/space` only when another filesystem is preferred.
Sort or DuckDB write failures are reported as resource errors rather than
correctness mismatches.

The live log and reports distinguish:

- `outer_reordered`: the OuterYan grouping differs from DuckDB's grouping;
- `outer_yan_selected`: the OuterYan candidate actually passed policy selection;
- `selected_plan`, `raw_cost_winner`, and `gate_result` as separate decisions;
- baseline, candidate-join, raw/weighted semi-join, and total estimated costs;
- the full cost formula and all join/SJ coefficient values;
- bitmap/hash kernel use; and
- a matched, median profiled single-thread query-latency sample (`Total-Time`)
  decomposed into native active-operator time for round-1 semi-joins, round-2
  semi-joins, real joins (`R3`), and the residual `Other`, with planned
  pair/new-filter counts and observed operator counts per round.

Every query is printed as a separate block beginning with a full-width
separator followed by exactly two lines. The first line contains correctness,
reorder, selected plan, kernel, phase profile, TM, and T1. The second line
contains decision, cost, gate, weight, and artifact details. Inapplicable
queries print `cost=[UNAVAILABLE]` instead of a formula filled with `NA` values.

R1, R2, and R3 are sums from DuckDB's native `OPERATOR_TIMING` tree, not
contiguous phase wall timers. R1 matches `SJ_BUILD_ROUND_1` and
`SJ_PROBE_ROUND_1`; R2 matches the corresponding round-2 names; R3 matches
physical join operator types. `Other` contains every unmatched operator plus
planning, scheduling, state setup, waits, profiler overhead, and other work not
represented by those operator timings. Integer-nanosecond arithmetic makes
`R1 + R2 + R3 + Other = Total-Time` exact. The log renders ratios as
percentages and reports matched physical-operator counts; the CSV retains
ratios in `[0,1]`.
Total-Time is DuckDB's high-resolution JSON query latency from a separate
profiled median sample, so instrumentation can make it differ from the
unprofiled `T1:on` median. T1/TM use fresh `-no-init` CLI processes, explicitly
disable profiling before the timer starts, and do not run the native profile
batch.
A zero-pair round is printed as
`NA(no-pairs,pairs=0)` rather than as a measured zero. The canonical CSV
contains one row per query; `.attempts.csv` is retained as an identical
single-attempt compatibility artifact. Timed-out queries are not retried.
`--capture-plans` also stores OFF/ON
EXPLAIN plans, optimizer traces, and per-step cost details.

Database builders reuse existing database files. To intentionally replace one
at another scale or with another graph dataset, set `FORCE=1` explicitly:

```bash
TPCH_SF=1 FORCE=1 bash auto_test/build_db.sh tpch
GRAPH_DATASET=wiki FORCE=1 bash auto_test/build_db.sh graph
```

The JOB builder downloads missing parquet files with `curl`, caches them under
`job_data/`, and loads them locally. It does not require remote `httpfs` scans.

## Tracing and runtime diagnostics

Tracing is available in release and debug builds. The helper runs one query
against an existing database and records the OuterYan stages selected by
`DUCKDB_OYTRACE`:

```bash
bash auto_test/trace_outer_yan.sh \
    --bin build/release/duckdb \
    --db graph_db \
    --file auto_test/outerjoin_query/graph/line_N3_mixB_s67.sql
```

Useful runtime controls are:

- `DUCKDB_OYTRACE=/path/to/trace.txt`: record optimizer stages and the final
  machine-readable candidate decision;
- `DUCKDB_OY_FORCE_CANDIDATE=1`: diagnostic correctness mode that forces a
  complete, applicable, non-proven-empty OuterYan candidate past grouping and
  cost selection;
- `DUCKDB_SJ_KERNEL_TRACE=1`: print the selected bitmap/hash kernel per filter;
- `SET VARIABLE outer_yan_bitmap_max_bytes = N`: set the per-filter bitmap
  budget (`0` forces hash fallback);
- `SET VARIABLE outer_yan_hash_fn = 'duckdb'|'murmur'`: select the hash function;
- `SET VARIABLE outer_yan_stats_prefilter = true|false`: enable or disable the
  optional statistics prefilter.

`DUCKDB_OY_SIMPLIFY_SCAN_FILTERS=1` is an experimental, generally unsound
measurement switch. It must not be enabled for correctness conclusions.

For a one-command build/data/experiment workflow, run
`bash auto_test/run_all.sh`. Existing databases are reused unless explicitly
rebuilt, and arguments after `run_all.sh` are forwarded to
`experiment_onoff.sh`.

---

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="logo/DuckDB_Logo-horizontal.svg">
    <source media="(prefers-color-scheme: dark)" srcset="logo/DuckDB_Logo-horizontal-dark-mode.svg">
    <img alt="DuckDB logo" src="logo/DuckDB_Logo-horizontal.svg" height="100">
  </picture>
</div>
<br>

<p align="center">
  <a href="https://github.com/duckdb/duckdb/actions"><img src="https://github.com/duckdb/duckdb/actions/workflows/Main.yml/badge.svg?branch=main" alt="Github Actions Badge"></a>
  <a href="https://discord.gg/tcvwpjfnZx"><img src="https://shields.io/discord/909674491309850675" alt="discord" /></a>
  <a href="https://github.com/duckdb/duckdb/releases/"><img src="https://img.shields.io/github/v/release/duckdb/duckdb?color=brightgreen&display_name=tag&logo=duckdb&logoColor=white" alt="Latest Release"></a>
</p>

## DuckDB

DuckDB is a high-performance analytical database system. It is designed to be fast, reliable, portable, and easy to use. DuckDB provides a rich SQL dialect with support far beyond basic SQL. DuckDB supports arbitrary and nested correlated subqueries, window functions, collations, complex types (arrays, structs, maps), and [several extensions designed to make SQL easier to use](https://duckdb.org/docs/current/sql/dialect/friendly_sql.html).

DuckDB is available as a [standalone CLI application](https://duckdb.org/docs/current/clients/cli/overview) and has clients for [Python](https://duckdb.org/docs/current/clients/python/overview), [R](https://duckdb.org/docs/current/clients/r), [Java](https://duckdb.org/docs/current/clients/java), [Wasm](https://duckdb.org/docs/current/clients/wasm/overview), etc., with deep integrations with packages such as [pandas](https://duckdb.org/docs/guides/python/sql_on_pandas) and [dplyr](https://duckdb.org/docs/current/clients/r#duckplyr-dplyr-api).

For more information on using DuckDB, please refer to the [DuckDB documentation](https://duckdb.org/docs/current/).

## Installation

If you want to install DuckDB, please see [our installation page](https://duckdb.org/docs/installation/) for instructions.

## Data Import

For CSV files and Parquet files, data import is as simple as referencing the file in the FROM clause:

```sql
SELECT * FROM 'myfile.csv';
SELECT * FROM 'myfile.parquet';
```

Refer to our [Data Import](https://duckdb.org/docs/current/data/overview) section for more information.

## SQL Reference

The documentation contains a [SQL introduction and reference](https://duckdb.org/docs/current/sql/introduction).

## Development

For development, DuckDB requires [CMake](https://cmake.org), Python 3 and a `C++17` compliant compiler. In the root directory, run `make` to compile the sources. For development, use `make debug` to build a non-optimized debug version. You should run `make unit` and `make allunit` to verify that your version works properly after making changes. To test performance, you can run `BUILD_BENCHMARK=1 BUILD_TPCH=1 make` and then perform several standard benchmarks from the root directory by executing `./build/release/benchmark/benchmark_runner`. The details of benchmarks are in our [Benchmark Guide](benchmark/README.md).

Please also refer to our [Build Guide](https://duckdb.org/docs/current/dev/building/overview) and [Contribution Guide](CONTRIBUTING.md).

## Support

See the [Support Options](https://duckdblabs.com/support/) page and the dedicated [`endoflife.date`](https://endoflife.date/duckdb) page.
