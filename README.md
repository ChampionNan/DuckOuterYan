# OuterYan

Anonymous research artifact based on DuckDB. OuterYan explores join reordering,
two-round semi-join reduction, aggregate pushdown, and bitmap/hash filter kernels
for queries containing inner and outer joins. Applicability and plan selection
are determined by the current optimizer source.

## Build

Use CMake, Ninja, Python 3, and a supported C++ compiler. Build a release binary
with the benchmark data generators enabled:

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
```

The CLI is `build/release/duckdb`. For assertions and focused C++ tests, use
`GEN=ninja make debug`. Performance measurements require a release build.

## Benchmark inputs

The current workload contains **350 SQL queries**: SGPB 67, TPC-H 87,
TPC-DS 87, and JOB 109. SGPB uses the internal family key `graph` (61 Bitcoin
and 6 Epinions queries). The workload contains 244 non-aggregate result queries
and 106 aggregation queries; input shapes are 121 left-deep, 124 right-deep,
and 105 bushy expressions. Queries and their manifest are in
[`auto_test/outerjoin_benchmark/benchmark/`](auto_test/outerjoin_benchmark/benchmark/).
Source queries, historical query definitions, and declarative generation policies
are retained because the generator uses them to reproduce the workload.

This is a historically curated, performance-conditioned workload. Its fixed
membership must not be described as an independently selected evaluation sample.
The repository contains query definitions and selection provenance, without
historical runtime observations or performance claims. Measure each new run
against the exact SQL identities in its manifest.

The default runner uses these committed queries unchanged. To explicitly regenerate
and verify the workload without running experiments:

```bash
bash auto_test/run_all.sh --prepare-only
```

The generator does not read experiment outputs. Start validation with a small
sample before running the complete corpus:

```bash
TPCH_SF=1 TPCDS_SF=1 bash auto_test/build_db.sh all
bash auto_test/experiment_onoff.sh --only graph --limit 3
```

The default experiment scales are TPC-H SF50 and TPC-DS SF50; the first command
explicitly requests smaller databases. Existing database files are reused.
Set `TPCH_DB`, `TPCDS_DB`, `GRAPH_DB`, `GRAPH_EPINIONS_DB`, and `JOB_DB` to override
paths. Dataset generation, downloads, and a complete experiment can be expensive.

## One-command experiment

Install Python 3.10+ and the report dependencies with
`python3 -m pip install -r auto_test/report_requirements.txt`. Dataset preparation
downloads public SNAP graph files and JOB Parquet tables when absent, and generates
TPC-H/TPC-DS through the built-in extensions. Network access and sufficient disk
space are required; existing configured databases are reused.

For an intentional complete run (potentially many hours):

```bash
bash auto_test/run_all.sh
# Reuse existing release binary and databases, using committed queries:
bash auto_test/run_all.sh --skip-build --skip-data
# Explicit query code generation/verification, then build + data + test + report:
bash auto_test/run_all.sh --generate-queries
# Generate and verify only; no benchmark execution or downloads:
bash auto_test/run_all.sh --prepare-only
# Inspect the command sequence without writes or executions:
bash auto_test/run_all.sh --dry-run
```

The entry point validates the existing SQL/manifests without regenerating them,
builds/reuses release and databases, runs the benchmark, and publishes statistics
and PDF/PNG figures. It does not generate LaTeX. With `--generate-queries`, it calls
the query generator and regenerates twice in isolated directories to verify
byte-identical SQL/manifests/query lists before the normal build/test stages.
This reconstructs the fixed workload; it does not select new queries from runtime
results. Default protocol: SF50 for TPC-H/TPC-DS, 32 threads, five unprofiled
post-warmup executions (median), separate profiles, 600 seconds **per execution
per engine**. Full correctness comparison is off in this performance workflow;
use `--check-correctness` to enable it. The underlying harness still defaults to
correctness checks when invoked directly. `--threads` and `--runs` change those
settings explicitly. Database environment overrides remain supported.

Reports are written to `auto_test/results/plots/YYYYMMDD/`. Original run CSV/TXT
and profiles remain under `auto_test/results/`. Each new run is reported alone;
no historical measurements are silently merged. Reprocess a completed run with:

```bash
bash auto_test/run_all.sh --report-only --csv auto_test/results/EXACT_RUN.csv --date YYYYMMDD
```

The current reporting rule excludes any OuterYan timeout. A DuckDB-only timeout
uses 600 seconds only when OuterYan has a completed measurement; verified
unexecuted native-plan fallbacks contribute a speed-up of 1x, not invented
absolute runtimes. Measured and substituted results remain distinguishable.
The 21 both-engine timeout definitions removed from the active set remain in
the archived predecessor. This frozen curation does not automatically remove
new timeouts or slow results from a future run.

See [`auto_test/README.md`](auto_test/README.md) for configuration, subset runs,
diagnostics, and report generation.

## Correctness and plan selection

OFF disables only OuterYan; ON enables the normal optimizer list:

```sql
SET disabled_optimizers = 'outer_yan'; -- OFF
SET disabled_optimizers = '';          -- ON
```

Correctness checks execute the bare query and compare complete result multisets.
Do not wrap queries in `CREATE TABLE AS` or `COPY`, or add `LIMIT`: those changes
can produce a different plan. The harness also records whether OuterYan was
selected, timed out, or fell back to DuckDB.

OuterYan compares its candidate with DuckDB's normally optimized join grouping.
An identical grouping keeps the DuckDB candidate. Cost gates, applicability
checks, and semi-join scheduling are source-level research controls. Keep both
reduction rounds and build/probe dependencies intact when changing the engine.

## Focused checks

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s auto_test -p 'test_*.py'
build/debug/test/unittest "[outer_yan]"
build/debug/test/unittest test/sql/optimizer/outer_yan/bitmap_budget.test
```

Script tests exercise corpus generation and the harness without a full timed
benchmark. Some report tests require NumPy, pandas, and Matplotlib. Upstream
`data/` and SQL test fixtures are test inputs, not generated experiment outputs.

## Repository and publication policy

Keep engine code, tests, benchmark SQL, required scripts/configuration/templates,
reproduction documentation, and license notices. All experiment outputs belong
under ignored `auto_test/results/`: logs, correctness exports, EXPLAIN plans,
traces, profiles, timing CSVs, statistics, figures, and rendered paper fragments.
There are no exceptions for selected results or paper examples. For a custom
output path, use an ignored directory or a location outside the repository.

Local databases, downloaded datasets, build products, caches, and agent settings
are also ignored. Query manifests and frozen selection policies describe inputs;
they must not embed measured runtimes, observed speedups, or machine identities.
Report templates contain placeholders rather than recorded results.

Check the publication tree and create an archive without Git history or local
outputs using:

```bash
python3 scripts/anonymous_source.py --check
python3 scripts/anonymous_source.py --output /tmp/outeryan-source.tar.gz
```

An existing development checkout retains its original Git history and local
configuration. Publish the checked source archive, or create a separate release
branch with a fresh root commit and anonymous author and committer metadata.
Point any anonymous repository mirror at that release branch. Do not distribute
the development checkout's `.git` directory or its historical commits. No source
export rewrites local history.

## Source layout and attribution

- `src/optimizer/outer_yan/`: optimizer IR, passes, and plan construction.
- `src/execution/operator/join/`: join execution and semi-join filters.
- `auto_test/`: benchmark generation, execution, and reporting tools.
- `test/optimizer/outer_yan/` and `test/sql/optimizer/outer_yan/`: focused tests.
- `benchmark/`, `extension/`, and `third_party/`: retained DuckDB components.

DuckDB's upstream attribution and third-party notices remain intact. See
[`LICENSE`](LICENSE), [`CITATION.cff`](CITATION.cff), and the component licenses.
