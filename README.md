# Yannakakis<sup>+</sup>

## Build

A `Makefile` wraps the build (same as upstream DuckDB). For all targets and flags
see the [DuckDB Build Configuration Guide](https://duckdb.org/docs/stable/dev/building/build_configuration.html).

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

## Testing the OuterYan optimizer

All test/benchmark scripts live in [`auto_test/`](auto_test/) — see
[auto_test/README.md](auto_test/README.md) for the full reference (data/DB build,
the disk-safe in-engine bench compare, single-query compare, tracing). Main steps:

```bash
export DUCKDB_BIN="$PWD/build/release/duckdb"

# 1. CORRECTNESS — OuterYan ON vs OFF, per query (set-based equivalence diff).
#    Suites: select | agg | tpch | tpcds | equiv (select+agg) | bench (tpch+tpcds) | all
bash auto_test/compare_equal_batch.sh all > compare_equal_batch_results.txt 2>&1
grep -E '❌ FAIL|⚠️' compare_equal_batch_results.txt        # any failures

# TPC-H/DS scale factor defaults to 10; override (and rebuild the DB) per run:
rm -f tpch_db* tpcds_db*; TPCH_SF=1 TPCDS_SF=1 bash auto_test/compare_equal_batch.sh bench

# 2. PERFORMANCE — gate on correctness, then time OFF vs ON (release binary only).
bash auto_test/experiment_onoff.sh --rscale 100000          # -> experiment_onoff_results.txt
bash auto_test/experiment_semijoin.sh                       # -> experiment_semijoin_results.txt

# 3. DEBUG a wrong answer — dump every optimizer pass for a query.
bash auto_test/trace_outer_yan.sh -q "SELECT ...;"          # -> oy_trace.txt
```

The databases (`equiv_db`, `tpch_db`, `tpcds_db`) and `*_results.txt` are built in
the repo root and are git-ignored.

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
