# DuckYanOuter benchmark tools

Run commands from the repository root. This directory contains reusable scripts,
benchmark SQL, input manifests, and configuration. Experimental outputs are local
artifacts and are never part of the published source tree.

## Workload and reproducibility

`outerjoin_benchmark/benchmark/` contains 321 queries: SGPB/Graph 67, TPC-H 86,
TPC-DS 61, and JOB 107. `manifest.csv` records query identity, content hashes,
dataset routing, join structure, and predicate parameters. Query lists and
`aliases.csv` support explicit subsets and historical name resolution.

The workload is historically curated and performance-conditioned. Frozen
selection policies retain the chosen identities, reasons, and selection rules;
they do not contain historical timing observations. Their membership is an input
to generation, not evidence of current performance. All new measurements must
identify the exact query content and execution settings.

The current cohort retains 282 of the 306 historically OuterYan-selected queries:
21 queries with both engines timed out and the user-specified JOB 10a right-deep
COUNT query with measured speedup below 0.7x have been removed. The user also
requested removal of the minimum-speedup TPC-H and JOB queries on 2026-10-15:
TPC-H `th_real_custdist` left-deep high and JOB SQLStorm 11914 bushy high COUNT.
These are outcome-conditioned exclusions, not optimizer improvements. The retained set
includes 6 three-relation queries and 4 DuckDB-only timeouts.
It also keeps 39 non-three-relation `COST_DUCKDB_BETTER` controls (Graph 16,
TPC-H 7, TPC-DS 16). The original 65 controls were chosen by family-count balancing in the initial
371-query cohort, then selectivity tier, tree shape, source, relation count, and
query type, without ranking runtime or speedup. On 2026-10-15, TPC-DS controls
were reduced from 42 to 16, retaining one per `source_seed` and `tree_shape`.
Smaller groups are considered first, semantic tiers are balanced, and SHA256
of the fixed revision plus query ID breaks ties. This grouping deliberately
ignores selectivity and join-type variations; it does not assert identical
optimized join trees or SQL semantics. No measured runtime or speedup is used.
This control deduplication leaves selected membership and non-TPC-DS controls unchanged. JOB now has 107 selected queries and no
additional controls. Other fallbacks are archived, including all `DUCKDB_PLAN`,
`INAPPLICABLE`, and uncertainty-guard cases. `plan_cohort.csv` records the
historical selection category, not a guarantee about a future optimizer run.

All 720 predecessor definitions remain in
`outerjoin_benchmark/revisions/pre_plan_cohort_20261014/benchmark/`.
`sources/plan_cohort_20261014.json` pins the exact retained membership.
`sources/cohort_selectivity_20261015.json`, applied by `cohort_query_updates.py`,
pins six approved definitions: five active TPC-H updates and one retired JOB
update retained for provenance. Regeneration applies these definitions, rather
than restoring the predecessor predicates:

| Active short ID | Frozen definition |
| --- | --- |
| A-H-B-12 (pilot A-H-B-07) | SQLStorm 25509 bushy COUNT: order dates 1992-01-01 through 1992-08-27 (medium) |
| G-H-LD-05 | `th_real_custdist`: duplicate the 1992-01-01 through 1994-04-19 order-date filter on the orders input, retaining the outer WHERE (medium) |
| Q-H-LD-36 | SQLStorm 17751 left-deep: ship dates 1996-07-05 through 1996-12-31; renamed from `sel_high` to `sel_medium` |
| A-H-RD-10 | TPC-H Q8 right-deep grouped COUNT: order dates 1995-01-01 through 1995-04-20 (low) |
| A-H-RD-11 | TPC-H Q8 right-deep grouped COUNT: order dates 1992-01-01 through 1994-07-18 (medium) |

The archived JOB SQLStorm 11914 high-tier bushy COUNT definition uses production
years 2003 through 2011. That query is retired, not regenerated into the active set.
Content hashes, full query IDs, predicate bands, and candidate provenance are pinned
in the policy; short IDs are only display labels. The active workload remains 321
queries. SQL generation is independent of the availability of measurement CSVs,
and does not guarantee a minimum speed-up in subsequent measurements.
The JOB 10a right-deep COUNT slot
was subsequently retired by explicit user request because no measured candidate reached 0.7x.
The old SQL stays in the archive, source measurement hashes remain recorded,
and regeneration does not read result CSVs. Future speedups are not guaranteed.
The harness still skips timing verified DuckDB fallbacks. For this cohort's
summary, those 39 queries contribute a policy-default speedup of 1x, not a timing
measurement. DuckDB-only timeouts contribute 600 seconds on the DuckDB side only
when OuterYan has a completed measurement and the recorded DuckDB limit is 600 s.
This is a timeout-limit proxy, not a measured pair or a proven post-warmup bound.
OuterYan timeouts remain excluded. Raw records and timeout flags are preserved.
Regenerate the current local historical report (requires its pinned source CSVs):

```bash
bash auto_test/run_all.sh --report-only --date 20261014
```

Its effective-runtime totals include capped pairs but exclude unexecuted fallback
queries. Separate measured-only totals and maxima are also exported. Raw and
prefixed historical snapshots are preserved; the dated unprefixed statistics and figures
are refreshed by `publish_plan_cohort.py`. No historical timing file is needed
to generate the benchmark or to report an explicitly supplied new-run CSV.

`outerjoin_benchmark/sources/` and `outerjoin_benchmark/revisions/`
are generator dependencies. Historical SQL is retained
for reconstruction and identity checks. Do not ignore these directories or all
JSON/CSV/TXT files: many are essential inputs. Calibration parameters describe
fixed predicate bands. Runtime results remain ignored outputs.

```bash
# Rebuild the deterministic workload without reading results/.
python3 auto_test/gen_outerjoin_benchmark.py

```

## Main scripts

| Entry | Purpose |
|---|---|
| `run_all.sh` | Main entry point: build/data, test committed queries, publish statistics/figures; generation is opt-in |
| `build_db.sh` | Create or reuse Graph, TPC-H, TPC-DS, and JOB databases |
| `experiment_onoff.sh` | Bare-query correctness, plan selection, profiling, and timing |
| `gen_outerjoin_benchmark.py` | Generate the frozen workload |
| `verify_benchmark_reproduction.py` | Regenerate twice without executing queries; check all input bytes |
| `record_reproduction_run.py` | Called by `run_all.sh`: record source/binary/input hashes and run settings in ignored results |
| `report_plan_cohort.py` | Explicit timeout/default reporting, with raw times preserved |
| `publish_plan_cohort.py` | Current cohort statistics, figures and one generated table bundle |
| `gen_experiment_result.py` | Summarize run CSVs and generate figures/tables |
| `balanced_benchmark.py` | Fixed workload construction used by the generator and byte-identity validation |
| `aggregate_count_refresh.py` | Reconstruct pinned COUNT(*) variants; does not select new candidates |
| `pg_plan_comparison/` | PostgreSQL comparison queries, instrumentation patch, and runners |

`configs.sh`, `thread_sweep.sh`, `phase_profile.sh`, `benchmark_corpus.py`,
`balanced_benchmark.py`, `legacy_corpus.py`, and the workload transformation
modules are shared dependencies. `test_*.py` files verify the retained generators,
harness and reporting policies. `benchmark_test_fixtures.py` supplies
their source fixtures. `graph_dataset_policy.py` validates the pinned dataset
definitions used by Graph generation; it does not generate retest candidates.

One-off tuning/retest launchers, old log recovery, standalone selectivity auditing,
optimizer debug scripts, legacy corpus generation, dynamic candidate qualification,
memory experiments, manuscript generators,
and exploratory PG searches are retired and available in Git
history. Frozen definitions and their reconstruction modules remain: they apply
fixed SQL identities, not a new search or speed-up-based selection on each run.
The obsolete `outerjoin_query_old/`, standalone `diagnostics/`, and `pg_oj_trace/`
directories are not required. `paper_examples/` is local-only and excluded from
version control and anonymous source exports.
Use `run_all.sh --report-only --csv EXACT_RUN.csv` for a new complete run.
`gen_experiment_result.py` retains the complete-pair policy for subset reports;
do not mix its headline statistics with the current cohort report.

Run-recording and reporting tools may include the caller's local paths and host
in ignored output files. These outputs are not part of the anonymous source
artifact. Never publish a local results directory without reviewing its metadata.

## One-command workflow

```bash
# Clean Linux clone: isolated Python + query generation + build + data + full experiment/report.
bash auto_test/run_all.sh --bootstrap --generate-queries
# Optional manual environment instead of --bootstrap:
python3 -m pip install -r auto_test/report_requirements.txt
# Expensive: the complete active workload, release build and data preparation.
bash auto_test/run_all.sh
# Existing SF50 databases and release binary; no rebuild or data download.
bash auto_test/run_all.sh --skip-build --skip-data
# Explicit query code generation + byte verification, followed by the complete experiment.
bash auto_test/run_all.sh --generate-queries
# No query execution: deterministic generation and two byte-identical checks.
bash auto_test/run_all.sh --prepare-only
# No writes or executions: display the planned commands.
bash auto_test/run_all.sh --dry-run
```

This is the complete **main benchmark** workflow. It includes the phase and
optimizer profiles collected by the timing harness, followed by summary tables
and both performance figures. PostgreSQL plan comparison is a separate experiment
and is not launched by this command.

Cold-start prerequisites: Git, Bash, curl, tar, SHA256 tooling, CMake, Ninja,
Make and a C++17 compiler. No Python 3.10+ installation or sudo is needed with
`--bootstrap`: uv 0.8.22 (archive checksum verified) installs CPython 3.11.13 and
the exact versions in `reproduction_requirements.txt` into ignored
`results/environment/`. Subsequent invocations automatically reuse this Python.
Build concurrency defaults to 8; set `JOBS=N` to bound both Make and CMake/Ninja.
The bootstrap and data downloads use HTTPS and stop on download/hash errors.

`prepare_reproduction_data.py` prepares **five** independent database files:
Bitcoin, Epinions, TPC-H SF50, TPC-DS SF50 and JOB. `data_checksums.json` pins the
normalized SNAP inputs and the 21 JOB Parquet inputs used by this workload.
Existing mismatching cache files are preserved and rejected, never silently
overwritten. A fresh database is built in a temporary directory on its target
filesystem, checked for required tables/primary keys and positive row counts,
then published with a `.reproduction.json` sidecar. Matching existing sidecars
are validated on reuse. Legacy databases without a sidecar are not silently
adopted: use new database paths for verified preparation, or `--skip-data` only
after an independent data/scale check. No foreign keys are invented.

Each run records `results/run_all_<timestamp>.environment.json` with the commit,
tracked changes, binary/SQL-manifest hashes, dataset sidecars, Python/package
versions, host and CLI settings. SQL and metadata must reproduce byte-for-byte;
timings and optimizer choices are remeasured, not forced to historical values.
Generation and fresh-run reporting require no prior results, plots or databases.
This verifies the fixed curated workload, not an independently sampled workload.

By default the runner reads and validates the committed queries without generating
or replacing SQL. `--generate-queries` calls `gen_outerjoin_benchmark.py` (the query
code generator), then `verify_benchmark_reproduction.py`, before building and testing.
Verification regenerates into two temporary directories and checks all SQL, manifests,
and query lists byte-for-byte. `--prepare-only` performs only that generation and
verification. Neither mode reads timing outputs to select query definitions. The
frozen policy, rather than arbitrary per-family/batch parameters, defines this workload.
Engine code generation is handled by the normal release build; `--skip-build` skips it.
The verification artifact is `results/run_all_TIMESTAMP.query_reproduction.json`
(or the explicit `--output-dir`). It records the active manifest hash, all 345
benchmark-file hashes, and the result of two independent regenerations. The
file set includes all 321 SQLs plus their manifests and query lists. A successful
`--prepare-only` verifies query reproduction only: it does not claim that downloads,
compilation or the full timed workload have run on that machine.

The default one-command performance protocol uses 32 threads, five post-warmup
timings per configuration (median), one separate profile per side, independent
600-second statement limits, and no complete-result correctness comparison.
Use `--check-correctness` for bare-query equivalence checks. No wrapper query,
new LIMIT, or other SQL change is introduced by this entry point. The underlying
harness performs additional plan/kernel diagnostics; those are not timing samples.
This runner does not SSH, commit, push, or start an experiment in the background.

`--threads N` (or a comma-separated sweep), `--runs N` (positive odd),
`--date YYYYMMDD`, and `--output-dir DIR` are explicit options. The current reporting
policy only substitutes DuckDB timeouts whose recorded limit is 600 seconds;
non-600 limits cannot be mixed into that statistic. `--skip-build` must use a
release binary for performance conclusions.
`TPCH_SF`, `TPCDS_SF`, and database path overrides work as below. Existing explicit
database paths must match the desired scale; setting SF does not convert them.

Fresh runs are published using only the exact CSV emitted by that invocation.
The reporter rejects duplicate/missing/extra query IDs and SQL-hash mismatches.
It never fills missing queries with historical measurements, and uses actual
plan decisions from the new run rather than assuming the frozen historical role.
Failed/timed-out observations remain in `current_results.csv` even when excluded
from performance statistics. A failed experiment's nonzero status is preserved.

```bash
# Update reports only; does not execute workload SQL or prepare data.
bash auto_test/run_all.sh --report-only \
  --csv auto_test/results/EXACT_RUN.csv --date YYYYMMDD
```

Local catalog metadata is read, read-only, to count attributes in optimization
representatives. Set `TPCH_DB`, `TPCDS_DB`, `GRAPH_DB`, and `JOB_DB` when reporting
on another machine. If unavailable, attribute counts are `--`, with warnings
in `report_metadata.json`; timings are not fabricated. Omit `--csv` only when
replaying the locally available pinned historical observations, not on a fresh
artifact checkout. `--no-figures` writes statistics only. The experiment and current
cohort report pipeline writes one `tables.tex` with generated tables, not manuscript
prose. There is no separate LaTeX option or per-table TeX output.

Each fresh full-cohort report contains exactly 13 files: two figures in PDF and
PNG (four files), seven CSV data tables, one JSON file for reporting rules,
source hashes and exclusions, and one `tables.tex`. It does not generate manuscript
text, an overview PDF, or duplicate per-query subsets. `--no-figures` writes the
nine table/metadata files. Existing files from older runs are not automatically deleted.

Full runs automatically publish only their own complete CSV under the current
cohort policy. Explicit subset/custom-corpus runs retain the harness's existing
batch statistics (legacy complete-pair policy), without mislabeling an incomplete
sample as a full-cohort report. Thread sweeps use separate `YYYYMMDD/tN/` report
directories, so one thread setting cannot overwrite another's figures.

### Output map

All publication outputs use `auto_test/results/plots/YYYYMMDD/`:

| Output | Meaning |
|---|---|
| `current_results.csv` | All active observations, raw profiles, effective times, stable query IDs and SQL hashes; filter `selected_plan`, `speedup_source`, `phase_summary_included`, `phase_figure_order` and `optimization_table_group` for subsets |
| `plan_cohort_statistics.csv` | All-query and selected-only statistics; measured/capped/default counts |
| `speedup_all_queries.pdf`, `.png` | Runtime pairs and reported ratios; timeout proxies use triangles, fallback ratios ordinary circles |
| `phase_breakdown_outeryan.pdf`, `.png` | First two displayed queries per family from the four-query phase-diverse, faster/equal sample |
| `phase_summary.csv` | Operator-time sums and percentages; per-query evidence remains in `current_results.csv` |
| `benchmark_composition.csv`, `benchmark_dimensions.csv` | Full/aggregate, tree-shape, source, size and selectivity counts |
| `shape_statistics.csv` | Input-expression shape comparison |
| `optimization_representatives.csv` | Up to twelve long-running faster/equal cases, table/attribute counts and `table_group` (`main` or `appendix`) |
| `report_metadata.json` | Reporting rules, source hashes, exclusions, selection rules and warnings |
| `tables.tex` | One generated bundle of runtime, phase, composition and optimizer tables; no manuscript prose |

Raw run CSV/TXT, logs, plan artifacts and optional generation verification stay
under `auto_test/results/`, outside the dated report directory. They are evidence
for reproduction, not additional paper outputs. CSV values are plain numbers,
without LaTeX formatting; use these tables when updating the manuscript.

The main runtime table includes all reportable queries. Phase tables use valid
OuterYan-selected operator profiles, including DuckDB-only timeouts when OuterYan
timing and profiling completed. Their percentages use actual summed operator
times, never the 600-second baseline substitute. Optimization tables and the
paired representative phase figure still require complete measured pairs. The runtime scatter cannot
plot fallback defaults because they have no absolute times; the ratio panel
includes them at 1x. The 600-second substitution does not erase the timeout flag
and is not a proven steady-state lower bound when warm-up timed out. Legacy
137.5x maxima are not pinned into a newer measurement automatically.

## Build and data

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
# Small TPC datasets; missing JOB inputs are downloaded from duckdb-data.
TPCH_SF=1 TPCDS_SF=1 bash auto_test/build_db.sh all
```

Use a release binary for performance conclusions. Existing databases are reused;
changing a scale variable never resizes an existing explicit database path.
`FORCE=1 bash auto_test/build_db.sh all` deliberately rebuilds databases.

The default Graph source is Bitcoin. Dataset-qualified Graph queries route to
Epinions through the manifest and `GRAPH_EPINIONS_DB`. Do not silently run those
queries against the Bitcoin database.

## Configuration

Environment variables override `configs.sh`; CLI flags override corresponding
environment values. Paths default to the current checkout, without a particular
username, host, or installation directory.

| Variable | Default | Meaning |
|---|---|---|
| `PYTHON_BIN` | `python3` | Python interpreter |
| `DUCKDB_BIN` | `build/release/duckdb` when available | CLI; configuration falls back to debug for development |
| `TPCH_SF`, `TPCDS_SF` | `50`, `50` | Generation scale and default database suffix |
| `TPCH_DB`, `TPCDS_DB` | `tpch_<SF>.duckdb`, `tpcds_<SF>.duckdb` | Explicit database overrides |
| `GRAPH_DB` | `graph_db` | Default Graph database |
| `GRAPH_EPINIONS_DB` | `graph_epinions.duckdb` | Epinions database |
| `JOB_DB` | `job_db` | JOB database |
| `OY_THREAD_COUNTS` | `32` | Sequential thread configurations; e.g. `16 32` |
| `OY_THREADS` | first configured count | Single-configuration override |
| `OY_RUNS` | `5` | Positive odd count of post-warmup timing executions |
| `OY_CHECK_CORRECTNESS` | `1` | Full bare-query multiset comparison |
| `OY_PROFILE` | `1` | Separate pre-timing OFF/ON profiles |
| `OY_CAPTURE_PLANS` | `0` | Capture plans, traces, and cost diagnostics |
| `OY_TIMEOUT_SECS` | `600` | Default timeout per statement and engine |
| `OY_DUCKDB_TIMEOUT_SECS`, `OY_OUTERYAN_TIMEOUT_SECS` | shared default | Independent engine limits |
| `OY_CORPUS` | `auto_test/outerjoin_benchmark/benchmark` | Query corpus |
| `OY_TMPDIR` | `auto_test/results/tmp` | Ignored scratch directory |

The main harness supports Python 3.7+, while some generation and analysis tools
use newer Python syntax. Use Python 3.10+ for the complete tool suite. Statistics
and plotting use NumPy, pandas, and Matplotlib; follow a tool's dependency errors
for optional analysis packages.

## Run a focused experiment

```bash
bash auto_test/experiment_onoff.sh --only graph --limit 3
bash auto_test/experiment_onoff.sh --only tpch --limit 3 --threads "16 32"
bash auto_test/experiment_onoff.sh --only all --query-type aggregate --limit 3
```

For a query-list file containing paths relative to the corpus:

```bash
bash auto_test/experiment_onoff.sh --only all \
  --query-list auto_test/outerjoin_benchmark/benchmark/tpch_tuning_promoted.txt
```

`--runs N` overrides sample count; `--timeout S` sets both engine limits;
`--duckdb-timeout S` and `--outeryan-timeout S` set independent limits.
`--capture-plans` enables diagnostic capture. Consult
`bash auto_test/experiment_onoff.sh --help` for the complete CLI.

For an intentional full run:

```bash
bash auto_test/run_all.sh
bash auto_test/run_all.sh --skip-build --skip-data
```

## Measurement semantics

OFF uses `SET disabled_optimizers='outer_yan'`; ON uses the empty disabled list.
Correctness executes the bare query, with no CTAS/COPY wrapper or added LIMIT.
The harness records full-result equivalence separately from plan selection.

Each timing configuration warms up, optionally profiles, then performs the
configured unprofiled executions. The default estimator is the median of five
post-warmup samples. Profiling and trace overhead must not be reported as normal
runtime. Debug timings are directional only.

Timeouts apply to each statement on each engine. An OFF timeout does not skip
ON. Current cohort reporting applies the 600-second substitution described
above, and excludes any ON timeout; raw statuses remain in ignored outputs.
A fallback is not a measured OuterYan execution, and a disabled
correctness check is not an equivalence proof. Inspect the report's cohort and
exclusion rules before interpreting summary numbers.

### Cost-gated versus forced-candidate experiments

Use the same committed SQL, release build, database scale, threads, and timing
protocol for both experiments. The ordinary run keeps the cost gate enabled:

```bash
env -u DUCKDB_OY_FORCE_CANDIDATE bash auto_test/run_all.sh
```

For an explicitly requested candidate-selection ablation, scope the existing
diagnostic override to that run only:

```bash
DUCKDB_OY_FORCE_CANDIDATE=1 bash auto_test/run_all.sh
```

This bypasses both the final cost gate and the same-grouping fallback for a
successfully constructed applicable candidate. It does not change cost-model
parameters or disable semantic applicability, failed-candidate, or proven-empty
guards. It therefore cannot promise that every SQL statement selects OuterYan.
The OFF configuration still disables OuterYan and measures native DuckDB; the
ON decision records `selection_mode=FORCE_OUTERYAN_DIAGNOSTIC` and
`cost_gate_applied=0`. Preserve these records and report this experiment
separately from the default optimizer. Results from different hosts are not a
controlled same-machine comparison of the gate's effect.

## Reports and artifact policy

```bash
bash auto_test/run_all.sh --report-only --csv auto_test/results/EXACT_RUN.csv --date YYYYMMDD
```

The default report directory is `auto_test/results/plots/<date>/`. Preserve raw
run CSVs when reprocessing; do not invent timings or merge observations from
changed SQL identities. A new complete experiment is reported as its own run.

All execution outputs must be under ignored `results/` directories or outside
the repository: CSV/TXT logs, correctness rows, EXPLAIN trees, debug traces,
profiles, local pilot comparisons, environment captures, statistics, plots,
and generated manuscript fragments. No selected/paper result is an exception.
Named legacy output locations are also ignored to prevent accidental inclusion.

Retained CSV/JSON/TXT files outside those directories must describe query inputs,
configuration, selection membership, or templates. They may contain thresholds
and predicate calibration parameters, but no measured runtime, observed speedup,
or personal machine identity. Never use `git add -f` to publish result files.

## Checks and anonymous export

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s auto_test -p 'test_*.py'
python3 scripts/anonymous_source.py --check
python3 scripts/anonymous_source.py --output /tmp/outeryan-source.tar.gz
```

The exporter checks the current publication files and excludes ignored outputs
and `.git`. Tests, source data fixtures, source licenses, and required templates
remain available. Original Git history is local development metadata and must
not accompany the anonymous source artifact.
