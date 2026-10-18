# DuckYanOuter

## Reproduce

```bash
bash auto_test/run_all.sh --bootstrap --generate-queries
```

Run from the repository root on Linux to prepare the environment, rebuild the
321-query benchmark, compile DuckOuterYan, prepare data, run experiments, and
generate statistics and PDF/PNG figures. Requires Git, Bash, curl, tar, CMake,
Ninja, Make, a C++17 compiler, network access, and sufficient disk space; a full
run takes hours.

### Parameters

| Parameter | Effect / default |
| --- | --- |
| `--bootstrap` | Install isolated Python 3.11.13 and pinned reporting dependencies; no sudo or system Python changes. |
| `--generate-queries` | Rebuild and byte-verify the fixed 321 queries; omitted by default, which uses committed SQL. |
| `--threads N` | Execution threads; default **32**. |
| `--runs N` | Positive odd number of unprofiled post-warmup executions; default **5**, report the median. |
| `--timeout S` | Limit **each execution, per engine**, not all repetitions together; default **600 seconds**. |
| `--check-correctness` | Enable full result comparison; off by default in this performance workflow. |
| `--skip-build --skip-data` | Reuse an existing binary and independently verified databases. |
| `--no-figures` | Generate statistics without figures. |
| `--dry-run` | Preview stages without executing or writing files. |

TPC-H/TPC-DS default to **SF50** (`TPCH_SF` / `TPCDS_SF`); build parallelism
defaults to **8** (`JOBS`). Logs, CSVs, and profiles go to `auto_test/results/`;
statistics and figures go to `auto_test/results/plots/YYYYMMDD/`.
Each report includes one `tables.tex` containing generated tables only; no manuscript
sections are generated. The separate PostgreSQL comparison is not run.

## Step-by-step commands

The sections below explain the stages separately. They are optional if you use
the reproduction command above; run manual steps from the repository root in Bash.

### 1. Prepare the environment and queries

```bash
bash auto_test/run_all.sh --bootstrap --prepare-only
export PATH="$PWD/auto_test/results/environment/venv/bin:$PATH"
```

Installs the local Python environment, generates the benchmark, and verifies it
against two independent regenerations; no build, dataset download, or query execution.

- Generator: [gen_outerjoin_benchmark.py](auto_test/gen_outerjoin_benchmark.py), implemented in [balanced_benchmark.py](auto_test/balanced_benchmark.py).
- SQL and manifest: [auto_test/outerjoin_benchmark/benchmark/](auto_test/outerjoin_benchmark/benchmark/).
- Verification output: `auto_test/results/run_all_TIMESTAMP.query_reproduction.json`.

The fixed workload contains SGPB **67**, TPC-H **86**, TPC-DS **61**, and JOB **107**
queries. It was curated using historical performance, not independently sampled;
generation uses frozen definitions and policies, never experiment outputs.

### 2. Build

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
```

Builds `build/release/duckdb` with the TPC-H/TPC-DS generators enabled.
Use a release build for performance measurements.

### 3. Prepare data

```bash
DUCKDB_BIN="$PWD/build/release/duckdb" python3 auto_test/prepare_reproduction_data.py
```

Downloads checksum-verified Bitcoin, Epinions, and JOB inputs, and generates
TPC-H/TPC-DS databases. Matching databases with reproduction metadata are reused;
existing files are never overwritten.

| Environment variable | Default |
| --- | --- |
| `TPCH_SF`, `TPCDS_SF` | `50` |
| `TPCH_DB`, `TPCDS_DB` | `tpch_<SF>.duckdb`, `tpcds_<SF>.duckdb` |
| `GRAPH_DB`, `GRAPH_EPINIONS_DB` | `graph_db`, `graph_epinions.duckdb` |
| `JOB_DB` | `job_db` |

Keep the same overrides for preparation and execution. For legacy databases
without `.reproduction.json` metadata, use new paths or `--skip-data` after
independently checking their identity and scale.

### 4. Run experiments

```bash
bash auto_test/run_all.sh --skip-build --skip-data
```

Tests the committed queries with OuterYan disabled/enabled, then generates
statistics and figures for this run only. Warmup and profiling are excluded
from the five-run median; use the parameters above to override defaults.

For a small correctness check instead of the full experiment:

```bash
bash auto_test/run_all.sh --skip-build --skip-data --only graph --limit 3 --check-correctness
```

### 5. Regenerate statistics and figures

```bash
bash auto_test/run_all.sh --report-only --csv auto_test/results/EXACT_RUN.csv --date YYYYMMDD
```

Replace `EXACT_RUN.csv` and `YYYYMMDD` with the completed run and output date.
This does not execute queries; add `--no-figures` for statistics only.

Reporting excludes OuterYan timeouts; DuckDB-only timeouts use **600 seconds**
when OuterYan completed. Verified unexecuted native-plan fallbacks contribute
**1×**, with no invented absolute runtimes; substituted and measured results
remain distinguishable. New runs do not automatically remove slow queries.

## Check scripts

```bash
python3 -m unittest discover -s auto_test -p 'test_*.py'
python3 -m unittest discover -s test/scripts -p test_anonymous_source.py
```

Checks generation, execution/reporting scripts, and publication boundaries
without a full timed benchmark. More options: [auto_test/README.md](auto_test/README.md).

## Export source

```bash
python3 scripts/anonymous_source.py --check
python3 scripts/anonymous_source.py --output /tmp/outeryan-source.tar.gz
```

Exports checked source without Git history or local artifacts; the output archive
must not already exist. Results, logs, debug/trace outputs, databases, and LLM
helper files are ignored; source, query-generation inputs, and test fixtures remain.

For anonymous review, publish the checked archive or the anonymous release
history, not the development checkout's Git history or identifying repository URL.
DuckDB attribution and component licenses are retained: [LICENSE](LICENSE),
[CITATION.cff](CITATION.cff).

OpenAI Codex was used to assist in preparing the code.
