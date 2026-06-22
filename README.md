# Yannakakis<sup>+</sup>

## Prerequisites

Building needs CMake + Python 3 + a C++17 compiler; the build/test steps below use
`ninja`, and the test scripts use GNU `timeout` for the soft per-query timeout.
**Only the toolchain install differs by platform — every `make` and script command
below is byte-for-byte identical on Linux and macOS.**

| platform | install toolchain | `timeout` |
|---|---|---|
| **Linux** (Debian/Ubuntu) | `sudo apt install -y build-essential cmake ninja-build python3` | native (coreutils) |
| **Linux** (Fedora/RHEL)   | `sudo dnf install -y gcc-c++ make cmake ninja-build python3` | native (coreutils) |
| **macOS**                 | `xcode-select --install && brew install cmake ninja coreutils` | `gtimeout` (scripts auto-fall back) |

> **Case sensitivity:** Linux filesystems are case-sensitive; a wrong-case
> `#include "duckdb/Planner/…"` can compile on macOS (APFS) yet fail the Linux
> build. Match the on-disk casing exactly — this is the one real Mac→Linux gotcha.

## Build

A `Makefile` wraps the build (same as upstream DuckDB), identical on both platforms.
For all targets and flags see the
[DuckDB Build Configuration Guide](https://duckdb.org/docs/stable/dev/building/build_configuration.html).

```bash
GEN=ninja make release   # optimized -> build/release/duckdb   (use this for all testing)
GEN=ninja make debug     # debug     -> build/debug/duckdb     (failure-debugging only)
```

The TPC-H / TPC-DS correctness suites need the `dbgen` / `dsdgen` extensions
**statically linked**, so build the release binary with them (a plain
`make release` omits them and those suites self-skip):

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
```

## Testing the OuterYan Optimizer

All test/benchmark scripts live in [`auto_test/`](auto_test/) — see
[auto_test/README.md](auto_test/README.md) for the full reference. Summary:

### Scripts

| Script | Purpose |
|---|---|
| `auto_test/run_all.sh` | **One-shot**: build + data + experiment (Linux) |
| `auto_test/build_db.sh` | Build databases (graph, tpch, tpcds, job) |
| `auto_test/gen_queries.py` | Generate the query corpus (graph + bench) |
| `auto_test/experiment_onoff.sh` | Correctness + performance: ON vs OFF |
| `auto_test/trace_outer_yan.sh` | Dump optimizer passes for a single query |
| `auto_test/configs.sh` | Unified configuration (sourced by all scripts) |

### Quick Commands

```bash
# Build all databases (auto-detects & builds missing extensions):
bash auto_test/build_db.sh

# Run the ON-vs-OFF experiment (all families):
bash auto_test/experiment_onoff.sh

# Run only TPC-H family:
bash auto_test/experiment_onoff.sh --only tpch

# Run a SINGLE query by label (--pattern is a glob over the query label, which is
# the .sql file name without extension, under auto_test/outerjoin_query/<family>/):
bash auto_test/experiment_onoff.sh --only tpch --pattern 'oy_th_th_branch5a_v2'

# --pattern accepts wildcards, so it can also select a subset:
bash auto_test/experiment_onoff.sh --only graph   --pattern 'star_N4_*'   # all star N=4
bash auto_test/experiment_onoff.sh --only job     --pattern '*_agg?'      # the agg variants

# Run graph family with wiki dataset (28.5M edges):
GRAPH_DATASET=wiki bash auto_test/experiment_onoff.sh --only graph

# Debug a specific query (dump optimizer passes; needs debug binary):
bash auto_test/trace_outer_yan.sh --db graph_db \
    -q "SELECT * FROM R1 LEFT JOIN R2 ON R1.dst=R2.src;"
```

### Parameters (experiment_onoff.sh)

```
  -b, --bin PATH      duckdb binary
  -n, --runs N        timed iterations per config (default 10, median taken)
  -t, --timeout S     per-query timeout (seconds, default 300)
      --only FAMILY   graph | tpch | tpcds | job | bench | all
      --pattern GLOB  filter queries by label
      --exclude GLOB  skip matching queries ('|'-separated)
      --limit N       cap total queries
  -o, --out FILE      output file
```

### Output format (experiment_onoff.sh)

Results stream to two files under `auto_test/results/` (override with `-o`):

- `experiment_onoff_<timestamp>.txt` — the human-readable table below.
- `experiment_onoff_<timestamp>.csv` — the same data, one row per query, for plotting.

Each query produces one row. `T1` is single-thread (`threads=1`); `TM` is
multi-thread (`threads=$OY_THREADS`). Times are the median (seconds) of `--runs`
timed iterations; a speed-up is `off / on`, so **> 1.0 means OuterYan ON is faster**.

```
query                              reord? kernel  correct   note          T1:off     T1:on  T1:spd    TM:off     TM:on  TM:spd
----------------------------------------------------------------------
line_N3_mixB_s80                   No    bitmap  TRUE      OK            0.0123    0.0150   0.820    0.0044    0.0051   0.863
oy_jb_jb_bushy4a_v0                Yes   mixed   TRUE      OK            0.2100    0.0900   2.333    0.0700    0.0310   2.258
star_N4_mixA_s33                   No    hash    FALSE     NOT-EQUIV          -         -       -         -         -       -
```

| column | meaning |
|---|---|
| `query`   | query label (the `.sql` file name) |
| `reord?`  | did OuterYan change the join order vs OFF? `Yes` / `No` |
| `kernel`  | semi-join filter kernel OuterYan ran: `bitmap`, `hash`, `mixed` (both), or `-` (no SJ filter fired) |
| `correct` | `TRUE` iff the ON result multiset equals the OFF result (correctness gate) |
| `note`    | `OK` / `NOT-EQUIV` / `TIMEOUT` / `ERROR` — only `OK` queries are timed |
| `T1:off T1:on T1:spd` | single-thread off time, on time, speed-up (`off/on`) |
| `TM:off TM:on TM:spd` | multi-thread off time, on time, speed-up (`off/on`) |

The `kernel` column comes from the in-binary `DUCKDB_SJ_KERNEL_TRACE` diagnostic:
when that env var is set, each finalized semi-join filter prints
`[SJ_KERNEL] BITMAP` or `[SJ_KERNEL] HASH reason=<force_hash|budget0|ineligible|overflow>`
to stderr. The harness sets it for one classification run per query; the CSV's
`kernel_detail` carries the raw per-query counts as `b<N>h<M>`. The default kernel
is the dense **bitmap** for single-column INTEGER/BIGINT/UINTEGER/DATE keys; it
falls back to **hash** when the key is not bitmap-eligible (`ineligible`), the
bitmap byte budget is exceeded (`overflow`), or the budget is set to 0 (`budget0`,
via `SET VARIABLE outer_yan_bitmap_max_bytes = 0`).

The run ends with a summary:

```
queries=42  correct=40  incorrect/skipped=2  timed=40
kernel (correct queries): bitmap=31  hash=5  mixed=4
threads: single=1, multi=8
  No  (no reorder): n=18  mean speed-up(TM)=0.94   [expect <=1.0 — SJ overhead, no reorder]
  Yes (reorder):   n=22  mean speed-up(TM)=1.71   [may be >1.0 — reorder/reduction win]
```

### Option gates / tunables

All OuterYan behavior is controlled by these gates. Env vars are read in-process
(set them before launching `duckdb`, or `export` them in a harness like
`experiment_onoff.sh`); `SET VARIABLE` gates are per-session SQL.

**Environment variables**

| Gate | Values | Default | Effect |
|------|--------|---------|--------|
| `DUCKDB_OYTRACE` | a file path | unset | Dump every OuterYan pipeline stage (OT, simplify, semi-join pairs, DP order, OJT) to the file. |
| `DUCKDB_SJ_KERNEL_TRACE` | `1` | unset | Print `[SJ_KERNEL] BITMAP` / `[SJ_KERNEL] HASH reason=…` per finalized semi-join filter to stderr. |
| `DUCKDB_OY_SIMPLIFY_SCAN_FILTERS` | `1` / `0` | off | **Experimental, unsound — measurement only.** Also derive outer→inner null-rejection from predicates folded into `LogicalGet::table_filters`. A scan filter is applied *pre-join*, so it does not null-reject the join output (`q LEFT JOIN r ON q.id=r.id AND r.rx>5` keeps the LEFT join with `rx>5` in r's scan). Safe in practice only because the applicability gate rejects unary ON-clause predicates and all test queries put filters in `WHERE`; do not rely on it. |

**`SET VARIABLE` (per session)**

| Variable | Type | Default | Effect |
|----------|------|---------|--------|
| `outer_yan_stats_prefilter` | boolean | `false` | Use base-table min/max stats to skip the bitmap `TryBuild` scan when the implied bitmap would exceed the byte budget. |
| `outer_yan_bitmap_max_bytes` | integer | `16777216` (16 MiB) | Semi-join bitmap byte budget. `0` forces the hash kernel for every filter. |
| `outer_yan_hash_fn` | `'murmur'` \| `'duckdb'` | `'duckdb'` | Hash function used by the hash semi-join kernel. |

**PRAGMA**

| Pragma | Effect |
|--------|--------|
| `PRAGMA disabled_optimizers='outer_yan';` | Disable the whole OuterYan optimizer (falls back to the native join-order optimizer). Individual passes can be disabled too: `outer_yan_pre`, `outer_yan_dp`, `outer_yan_post`. |

### Complete Workflow (New Machine)

```bash
# 1. Clone
git clone <repo-url> DuckYanOuter && cd DuckYanOuter

# 2. One command does everything: build → data → experiment
bash auto_test/run_all.sh
```

Or step-by-step:

```bash
# Build with extensions
BUILD_TPCH=1 BUILD_TPCDS=1 BUILD_HTTPFS=1 GEN=ninja make release

# Build databases (auto-rebuilds binary if extensions are missing)
bash auto_test/build_db.sh all
#   graph_db  — SNAP bitcoin (default), ~24K edges → R1..R10
#   tpch_db   — TPC-H SF=100 via CALL dbgen(sf=100)
#   tpcds_db  — TPC-DS SF=100 via CALL dsdgen(sf=100)
#   job_db    — IMDb 21 tables via httpfs read_parquet (remote, ~1.75GB)

# Run experiment (correctness + dual-thread timing, median of 10 runs)
bash auto_test/experiment_onoff.sh

# (Optional) Larger-scale graph
GRAPH_DATASET=wiki bash auto_test/build_db.sh graph
bash auto_test/experiment_onoff.sh --only graph
```

**`run_all.sh` environment overrides:**

```bash
# Skip compilation (reuse existing binary):
SKIP_BUILD=1 bash auto_test/run_all.sh

# Skip data generation (reuse existing databases):
SKIP_DATA=1 bash auto_test/run_all.sh

# Custom scale + graph:
GRAPH_DATASET=wiki TPCH_SF=100 bash auto_test/run_all.sh --only graph
```

Outputs (git-ignored): `graph_db`, `tpch_db`, `tpcds_db`, `job_db`,
`graph_data/`, `auto_test/results/`.

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
