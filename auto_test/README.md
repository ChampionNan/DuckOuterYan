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
| `configs.sh` | Shared DuckDB, corpus, timing, and PGPlan defaults |
| `run_all.sh` | Build/data orchestration followed by the default DuckDB Original/OuterYan comparison; PGPlan is opt-in |
| `pgplan/` | PostgreSQL 16.2 setup, cached logical-tree capture/import, comparison experiment, and documentation |
| `build_db.sh` | Build or reuse graph, TPC-H, TPC-DS, and JOB databases |
| `gen_outerjoin_benchmark.py` | Generate the provenance-backed paper benchmark and its manifests |
| `gen_queries.py` | Reproduce the archived pre-design corpus under `outerjoin_query_old/` |
| `experiment_onoff.sh` | ON/OFF equivalence, plan decision, kernel diagnostics, and multi-thread timing |
| `audit_cost_gate.py` | Extract changed-grouping candidates and classify normal gate decisions against forced-candidate timings |
| `representative_queries.txt` | Ordered P0/P1 cross-family validation manifest, including runnable 3–7 relation cases |
| `trace_outer_yan.sh` | Write the optimizer-stage trace for one query |
| `outerjoin_query/` | Compatibility link to the provenance-backed benchmark core |
| `outerjoin_benchmark/` | 176-query active view, full 170-query core, 36-query industry evaluation, 28-query supplemental suite, manifests, and paper text |
| `outerjoin_query_old/` | 170 completed queries from the active pre-design corpus |
| `outerjoin_query_timeout/` | Recoverable archive of the 84 legacy timeouts from the August 10 run |
| `results/` | Generated text, CSV, trace output, and native phase profiles |

`trace_outer_yan.sh` has its own command-line/environment defaults and does not
source `configs.sh`.

## Current configuration

Environment variables override `configs.sh`; experiment CLI options override the
corresponding environment values.

| Variable | Current source default | Meaning |
|---|---:|---|
| `PYTHON_BIN` | `python3` | Python 3.7+ standard-library interpreter; may be an absolute repo-local path |
| `DUCKDB_BIN` | `build/release/duckdb` | Release CLI, with debug fallback if release is absent |
| `GRAPH_DATASET` | `bitcoin` | SNAP source used when `graph_db` is built |
| `TPCH_SF` | `100` | TPC-H scale used when `tpch_db` is built |
| `TPCDS_SF` | `100` | TPC-DS scale used when `tpcds_db` is built |
| `OY_THREAD_COUNTS` | `32` | One default configuration; explicit space/comma-separated sweeps also work |
| `OY_THREADS` | first configuration (`32`) | Scalar override to run only one thread count |
| `OY_TIMEOUT_SECS` | `1800` | Per-statement timeout; `0` disables it |
| `OY_BATCH_GRACE_SECS` | `30` | External timing-batch startup/serialization grace |
| `OY_RUNS` | `3` | Positive odd number of timed executions after one warm-up |
| `OY_PROFILE` | `1` | Separate ON phase profiling for correct OuterYan-selected queries; `0` skips it |
| `OY_CAPTURE_PLANS` | `0` | Save OFF/ON EXPLAIN, optimizer trace, and cost-step artifacts |
| `OY_CORPUS` | `auto_test/outerjoin_query` | Corpus root |
| `RUN_PGPLAN` | `0` | Set to `1` to opt into PGPlan generation and three-way comparison |
| `PGPLAN_SETUP` | `source` | PostgreSQL provider: repo-local source build, Docker, or an external DSN |
| `PGPLAN_SOURCE_DIR` | `postgres` | Repo-local PostgreSQL source/build root used by `source` mode |
| `PGPLAN_INSTALL_DIR` | `postgres/postgresql` | Repo-local PostgreSQL installation prefix used by `source` mode |
| `PGPLAN_PASSWORD_FILE` | `postgres/postgresql/.pgplan-password` | Mode-`0600` generated secret for managed source and Docker servers |
| `PGPLAN_CORPUS` | `auto_test/outerjoin_query` | Corpus whose selected queries receive validated cached or freshly captured PGPlan artifacts |
| `PGPLAN_SAMPLE_ROWS` | `1000` | Per-table PostgreSQL row cap for graph, TPC-DS, and JOB plan selection |
| `PGPLAN_PLAN_CACHE` | `auto_test/pgplan/plans` | Persistent validated typed-plan cache; override with `--plan-cache` |
| `PGPLAN_COMPARISON_MODE` | `both` | `both`, `pgplan-only` (`--skip1`), or `none` (`--performance-only`) |
| `PGPLAN_RUNS` | `OY_RUNS` (`3`) | Positive odd TM measured-run count after one warm-up; no single-thread batch |
| `PGPLAN_CORRECTNESS_MODE` | `target` | `target` compares complete target results; `bounded` is a diagnostic; `reuse` requires a sealed prior target receipt |
| `PGPLAN_CORRECTNESS_FROM` | empty | Prior corpus root used by correctness-only `reuse` mode |
| `PGPLAN_REUSE_FROM` | empty | Prior corpus root used to reuse both PGPlan artifacts and sealed correctness receipts |
| `PGPLAN_CORRECTNESS_GRAPH_ROWS` | `500` | Bounded-mode deterministic graph prefix |
| `PGPLAN_CORRECTNESS_JOB_ROWS` | `1000` | Bounded-mode deterministic JOB prefix |
| `PGPLAN_CORRECTNESS_MAX_RESULT_ROWS` | `2000000` | Bounded-mode builder preflight result cap |
| `PGPLAN_CORRECTNESS_QUERY_TIMEOUT_SECS` | `30` | Bounded-mode builder preflight timeout |
| `PGPLAN_CAPTURE_TIMEOUT_SECS` | `300` | PostgreSQL plain-`EXPLAIN` optimizer timeout; `0` disables it |
| `PGPLAN_TIMEOUT_SECS` | `OY_TIMEOUT_SECS` (`1800`) | Per DuckDB statement and requested correctness post-processing step |
| `SKIP_PG_DATA` | `0` | Set to `1` to forbid TPC-H SF0.01 loading/repair and require verified existing data |
| `DUCKDB_OY_FORCE_CANDIDATE` | unset | Set to `1` only to force a valid OuterYan candidate for correctness validation |

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

The default corpus is the timeout-filtered 176-query workload under
`outerjoin_benchmark/benchmark/`. The `outerjoin_query` compatibility link
points there. It contains 144 benchmark-derived queries and 32 evaluation
queries. The complete component views retain 170 core queries and 36 evaluation
queries (nine industry-inspired patterns plus all 28 pinned legacy OuterYan
wins, with one overlap). Thirty confirmed multithread timeout cases are removed
from the active view: 21 from the 0830/48-thread run and another nine from the
0908/32-thread run. The latter include the seven formerly protected graph bushy
and TPC-H Q9 star cases; those two family/pattern combinations are no longer
covered by the active set. Successful queries are not removed to improve scores. See
[`active_corpus_coverage.md`](outerjoin_benchmark/active_corpus_coverage.md)
for the evidence, exceptions, and before/after distributions.
Labels are SQL basenames without `.sql`; `--pattern` and `--exclude` match the
entire label using shell-glob syntax.

```bash
python3 auto_test/gen_outerjoin_benchmark.py
OY_CORPUS=auto_test/outerjoin_query \
  bash auto_test/experiment_onoff.sh --only all
```

Generation is deterministic and writes query-level provenance manifests. Active
query names use only `derived__` and `industry__`. In the complete components,
the 170 benchmark-derived queries and 27 legacy synthetic performance guards
use `derived__`; the nine
business-role patterns use `industry__`, including the one that is also a
pinned legacy win. Exact roles remain in the manifest rather than being encoded
as `*win` name variants. The benchmark-derived core has 170 queries (TPC-H 25,
TPC-DS 35, JOB 50, and SQLStorm 60), including 46 left-deep, 80 right-deep,
and 44 genuinely bushy graph-preserving applicability inputs. Of these, 158
use all-FULL vectors and 12 use mixed `alt` vectors. The evaluation under
`outerjoin_benchmark/industry_inspired/` is the
union of nine explainable legacy business patterns and all 28 correct queries
where the pinned August 10 run selected OuterYan with `tm_speedup > 1.0`. One
query belongs to both groups, so the corpus contains 36 unique queries. Its
manifest labels the two roles separately; performance-selected entries are not
claimed to be industry-derived. Before active timeout filtering, the full
206-query union contains 62 left-deep, 88 right-deep, and 56 bushy inputs. The
filtered core retains 41 left-deep, 70 right-deep, and 40 bushy inputs; all core
pattern categories remain covered, but benchmark family weights change.
Run the complete component (which bypasses active timeout filtering)
with:

```bash
OY_CORPUS=auto_test/outerjoin_benchmark/industry_inspired \
  bash auto_test/experiment_onoff.sh --only all
```

The historical generator remains
available as `gen_queries.py`; it writes to `outerjoin_query_old/` and applies
the 84 timeout exclusions pinned in `legacy_corpus.py`. Both generators use
this checked-in membership metadata, not local files under `results/`, so
regeneration works on a fresh checkout or another server. The same 28
performance-selected synthetic stress cases are also available as a focused
component view under `outerjoin_benchmark/supplemental`. See
`outerjoin_benchmark/README.md` for the transformation and terminology rules.
The active view additionally applies `benchmark_timeouts.py`, with exclusions
recorded in `outerjoin_benchmark/active_timeout_exclusions.csv`. This is a
separate policy from the 84 older historical exclusions and also requires no
local results file. Excluded SQL remains in its component source directory.

Query traversal is deterministic. Families are visited in the order selected by
the harness; `--only bench` means `tpch`, then `tpcds`, then `job`. Within each
family, SQL basenames are ordered bytewise (`LC_ALL=C`). A bushy-eligible seed
emits `bdmx`, `bmx`, `ldmx`, `rdmx`, and `rduX`; a bushy-ineligible seed emits
`alt`, `ldmx`, `rdax`, `rdmx`, and `rduX`. Here `X` is a legacy filename label;
this is only filename order, not a semantic progression. A `--query-list` file
overrides this order and is processed line by line.

### Core query variants

The suffix records the binary join-tree traversal. Primary/control vectors are
FULL (`F...F`) so they survive pre-OuterYan simplification; the 12 `alt`
queries retain mixed vectors. Older suffix stems remain for result-file continuity.

| Suffix | Tree and join labeling | Meaning |
|---|---|---|
| `ldmx` | Primary left-deep FULL tree | Primary left-deep traversal of the fixed graph. |
| `rdmx` | Primary right-deep FULL tree | Primary right-deep traversal of the fixed graph. |
| `bmx` | Connected bushy FULL tree | Tests bushy grouping without a cross product; emitted only when both root subtrees can contain at least two relations. |
| `bdmx` | Secondary connected bushy FULL tree | Uses another connected split/orientation of the same fixed graph. |
| `alt` | Alternate left-deep mixed tree | Replaces `bmx` when a true cross-product-free bushy tree is unavailable. |
| `rdax` | Secondary right-deep FULL tree | Replaces `bdmx` when the graph cannot form a true bushy root. |
| `rduX` | Alternate right-deep FULL tree | Starts at the opposite graph side; `X` is a legacy filename label and the manifest records the actual all-`F` vector. |

The core contains 46 left-deep, 80 right-deep, and 44 bushy queries. Every
grouping is independently specified because outer joins are not generally
associative. Global NULL-rejecting predicates remain selective, while the FULL
input labels ensure at least one outer edge remains when filter pushdown runs.
The two historical aggregate patterns in the active evaluation set are emitted
as detail projections so they do not bypass OuterYan.

The schema-only legacy queries are not included in any active benchmark
component. They remain in `outerjoin_query_old/` solely as historical inputs.

## Experiment pipeline

`experiment_onoff.sh` and `run_all.sh` use **32 threads only** by default.
Request a sequential sweep explicitly with `--threads "16 32"` or
`OY_THREAD_COUNTS="16 32"`; each configuration uses separate processes and
output files. Use `--threads 16` / `OY_THREADS=16` for a different single
configuration. Thread counts must be greater than one; CLI settings take
precedence. Database setup and query generation in `run_all.sh` happen only
once before any requested sweep.

For every selected query at each thread count, `experiment_onoff.sh` performs:

1. Execute the bare query with OuterYan OFF and ON, sort the emitted CSV files
   outside DuckDB, and compare the result multisets. A mismatch, error, or
   timeout is not timed. No SQL wrapper changes the optimized plan.
2. Run a traced `EXPLAIN` in a fresh process and read one `[OY_DECISION]` record.
3. If OuterYan was selected, run one kernel-classification execution and record
   bitmap/hash filter counts.
4. Time OuterYan OFF and ON at `threads=$OY_THREADS`. Each batch
   has one warm-up followed by `--runs N` timed executions; the median excludes
   the warm-up.
5. For correct queries whose ON plan selects OuterYan, collect a separate native
   JSON profile batch at the same thread count. This is enabled by default
   (`OY_PROFILE=1`); `--no-profile` or `OY_PROFILE=0` skips it, and `--profile`
   explicitly enables it. One profiled warm-up is followed by `--runs N` samples.
   The complete phase tuple from the median profile wall-latency execution is
   retained, rather than taking independent medians of its components.

All executions explicitly set the selected multi-thread count. Correctness,
diagnostics, and OFF/ON performance timing disable profiling. There is no
single-thread batch. Timing runs in fresh `-no-init` CLI processes using `.mode
trash`, which fully drains the bare query without measuring CSV formatting or
file output. Correctness and optional plan/cost diagnostics remain enabled.
Profile work adds a separate ON batch and never contributes to OFF/ON timing
medians or speed-up. A profile failure leaves valid timing pairs intact and
records `profile_status=ERROR`, unavailable phase values, and `PROFILE-ERROR`
in the note; partial JSON files and the CLI log remain available for diagnosis.

Bare-query equivalence can require temporary space comparable to several query
result sets. Temporary result and external-sort files default to
`<repo>/auto_test/results/tmp`. At
`/home/data/bchenba/DuckYanOuter`, this resolves to
`/home/data/bchenba/DuckYanOuter/auto_test/results/tmp` on the large `/home`
filesystem. The harness prints the resolved path and free capacity at run
start. Each experiment uses a separate `run_<timestamp>.*` subdirectory that
is removed on normal exit and Ctrl+C. Override `OY_TMPDIR` only when another
filesystem is preferred. A DuckDB or sort write failure is reported as
`ERROR` with its concrete stderr and is never classified as `NOT-EQUIV`.

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
strict_ratio_limit = 0.90 when semijoin_retained_cardinality_ratio < 0.90,
                     otherwise MAX_CANDIDATE_TO_BASELINE_RATIO
strict_threshold = strict_ratio_limit * baseline_cost

select OuterYan on the strict tier iff candidate_total <= strict_threshold
```

Cost formula V7 retains two consistency checks before that final comparison.
For fully reduced all-INNER candidates, every intermediate estimate is bounded
below by the largest reduced leaf in its subtree. For table filters that used
DuckDB's generic selectivity fallback, the candidate and baseline are also
scored with unfiltered base cardinalities; the gate uses whichever scenario
has the higher candidate/baseline ratio. These checks target false-positive
selections in the slow tail without globally tightening the `1.0` limit and
discarding unrelated wins.

The uncertain-filter amplification guard also rejects a candidate when the
largest input is at least `1000x` the uncertain filtered relation and the two
reducer rounds retain at least `99%` of estimated input cardinality. The trace
records the retention ratio, amplification, and guard result explicitly.

Cost formula V7 uses the full modeled semi-join row-work (`1.0 *
semijoin_raw_cost`) and a confidence-aware stretch tier without changing DP
enumeration. The earlier `0.50` semi-join discount admitted regressions in the
August 18 unified audit. Candidates whose reducer rounds are estimated to
retain less than `90%` of input rows must beat the baseline by at least `10%`;
this protects the strict tier when its apparent advantage depends on uncertain
reduction estimates. The relaxed ceiling is `1.20`, but it is available only when all
of the following planner-visible checks pass:

```text
no generic/default-filter upper-bound scenario
no uncertain-filter amplification guard
no active full-reduction cardinality lower-bound correction
candidate_join_cost < baseline_cost
candidate_join_input_rows <= 0.30 * baseline_join_input_rows
semijoin_retained_cardinality_ratio >= 0.95
```

`candidate_join_input_rows` and `baseline_join_input_rows` sum the left and
right cardinalities processed by every real join, approximating hash
build/probe work that the output-only join cost does not capture. An eligible
candidate whose total lies in `(1.0, 1.20] * baseline_cost` is selected with
reason `COST_OUTERYAN_STRETCH`. High-retention candidates otherwise retain the
strict `1.0` limit; lower-retention candidates use the guarded `0.90` limit.
These constants are experimental safety margins, not a runtime performance
guarantee.

The trace and CSV report two separate comparisons: `raw_cost_winner` compares
`candidate_total` directly with `baseline_cost`, while `gate_result` compares
`candidate_total` with `baseline_threshold`. `selected_plan` is the plan that
is actually returned and can differ because of same-grouping or proven-empty
policy decisions.

The policy knobs are `constexpr` members of `OuterYanOptimizer` in
`src/include/duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp`; they
are not environment variables or SQL settings. The current workspace selects
`GATED`, uses a semi-join ratio of `1.0`, a lower-retention limit of `0.90`,
a normal strict limit of `1.0`, and the confidence-gated `1.20` stretch ceiling
described above.
Rebuild the CLI after changing these source-level settings.

Set `SELECTION_MODE` to `SelectionMode::GATED` for the cost gate, or to
`SelectionMode::FORCE_OUTERYAN` to select every complete,
changed-grouping, non-proven-empty OuterYan candidate. Same-grouping,
inapplicable, failed, and proven-empty cases continue to use DuckDB in both
modes. The selected mode is written to `[OY_DECISION]`, TXT, and CSV output.

#### Force a same-grouping or cost-rejected candidate

The source-level `FORCE_OUTERYAN` mode still preserves the same-grouping
shortcut. Therefore `correct=TRUE selected=DUCKDB` does not validate the
OuterYan candidate. For a targeted correctness run, use the command-scoped
diagnostic override:

```bash
DUCKDB_OY_FORCE_CANDIDATE=1 \
bash auto_test/experiment_onoff.sh \
  --only tpcds \
  --pattern 'oy_ds_ds_bushy5b_v0' \
  --runs 3 \
  --capture-plans
```

The harness's OFF processes continue to use
`SET disabled_optimizers TO 'outer_yan';`. Its ON processes execute the
OuterYan candidate even if `outer_reordered=0` or `raw_cost_winner=DUCKDB`.
This override bypasses grouping equality and the cost gate only after the
candidate is known to be complete and the DuckDB baseline is not proven empty.
Aggregate/DISTINCT, inapplicable, failed, and proven-empty cases remain on
DuckDB.

A successful validation must report:

```text
correct=TRUE ... selected=OUTERYAN ...
decision=[mode=FORCE_OUTERYAN_DIAGNOSTIC
          reason=FORCE_OUTERYAN_DIAGNOSTIC
          ... gate=SKIPPED ... outer_yan_selected=1 ...]
```

#### Audit every changed-grouping candidate

Cost-gate evaluation is an offline two-run procedure. First run the corpus in
normal `GATED` mode. Extract forceable queries for which `outer_reordered=1`:

```bash
python3 auto_test/audit_cost_gate.py \
  --normal-csv auto_test/results/experiment_onoff_core_TIMESTAMP.csv \
  --write-query-list /tmp/outeryan_changed_queries.txt
```

Run that list again with the diagnostic candidate override. Both sides still
execute the bare query, and an incorrect candidate is never considered a
performance win:

```bash
DUCKDB_OY_FORCE_CANDIDATE=1 \
OY_CORPUS=auto_test/outerjoin_benchmark/core \
bash auto_test/experiment_onoff.sh \
  --only all \
  --query-list /tmp/outeryan_changed_queries.txt \
  --runs 3 \
  --capture-plans \
  --out auto_test/results/experiment_onoff_forced_TIMESTAMP.txt
```

Finally, join the normal and forced results:

```bash
python3 auto_test/audit_cost_gate.py \
  --normal-csv auto_test/results/experiment_onoff_core_TIMESTAMP.csv \
  --forced-csv auto_test/results/experiment_onoff_forced_TIMESTAMP.csv \
  --output auto_test/results/cost_gate_audit_TIMESTAMP.csv
```

The default symmetric materiality band treats a speedup of at least `1.10` as
faster, a speedup of at most `1/1.10` as slower, and values between those
bounds as neutral. It can be changed with `--material-speedup`. The report
derives speedup from the precise OFF and ON times rather than the rounded
speedup column, and classifies multi-thread (`tm`) and single-thread (`t1`)
measurements
separately. A selected faster plan is a true positive; a rejected faster plan
is a false negative; a selected slower plan is a false positive; and a rejected
slower plan is a true negative. A disagreement between `tm` and `t1` is marked
as thread-sensitive rather than collapsed into a single winner. Multi-thread
timing is the default primary metric and can be changed with
`--primary-metric t1`.

The audit also requires the normal row to be a consistent `GATED` decision,
the forced row to report a changed grouping under
`FORCE_OUTERYAN_DIAGNOSTIC`, and the effective pass, query identity, result
cardinality, formula, weights, and candidate cost inputs to agree. These checks
are a deterministic-rerun proxy; the current trace does not export a grouping
signature for direct comparison. Non-matching or incorrect rows are reported
as non-comparable rather than scored. A changed candidate whose DuckDB
baseline is proven empty cannot be diagnostic-forced, so it is excluded from
the query list and counted as `proven_empty_excluded`.

Normal and forced runs must use the same binary, corpus, database snapshot,
thread count, and run count. Because the result CSV currently stores medians
rather than confidence intervals over raw samples, these labels are
provisional; repeat apparent wins and regressions independently before tuning
the source-level gate constants.

`reorder=0` means that the two candidates have the same base-relation grouping;
it does not contradict `selected=OUTERYAN`. Use `kernel=bitmap(...)`,
`kernel=hash(...)`, `kernel=mixed(...)`, or `kernel=none(...)`, plus the saved
enabled plan and trace, to inspect the executed semi-join candidate. Keep the
variable command-scoped so later experiments return to the configured
`GATED`/`FORCE_OUTERYAN` policy automatically.

Decision reasons written to the trace and result files include:

| Reason | Meaning |
|---|---|
| `INAPPLICABLE` | OuterYan applicability check failed |
| `DUCKDB_AGGREGATE` | Query contains aggregation or DISTINCT and bypasses OuterYan |
| `DUCKDB_PLAN` | Candidate has the same grouping as DuckDB; use DuckDB |
| `DUCKDB_PROVEN_EMPTY` | DuckDB's proof copy eliminates all real join work; use DuckDB without SJs |
| `FORCE_OUTERYAN` | Changed candidate selected by the forced experiment mode |
| `FORCE_OUTERYAN_DIAGNOSTIC` | Complete candidate forced past grouping and cost selection for a targeted correctness run |
| `COST_OUTERYAN_BETTER` | Changed candidate passed the configured threshold |
| `COST_OUTERYAN_STRETCH` | High-confidence candidate passed the relaxed `1.20` stretch threshold |
| `COST_DUCKDB_BETTER` | Changed candidate exceeded the configured threshold |
| `COST_UNCERTAIN_FILTER_AMPLIFICATION` | Unknown-selectivity amplification guard rejected the candidate |
| `COST_UNAVAILABLE` | A finite comparison could not be produced |
| `OUTERYAN_FAILED` | OuterYan did not produce a complete candidate |

Aggregate and DISTINCT queries bypass OuterYan and use DuckDB's normal plan.
Semi-join operators are inserted only when a non-aggregate OuterYan candidate
is selected.

### Command-line options

```text
bash auto_test/experiment_onoff.sh [options]
  -b, --bin PATH      DuckDB CLI
  -n, --runs N        positive odd timed executions per configuration
  -t, --timeout S     per-statement timeout
      --threads LIST  multi-thread counts (default "32"; also accepts 16,32)
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
# Four small graph queries, one 16-thread smoke run
GRAPH_DATASET=bitcoin OY_THREADS=16 \
bash auto_test/experiment_onoff.sh \
  --only graph --pattern '*_N3_*_s0[15]' --limit 4 --runs 1 --timeout 60

# Two three-relation aggregate queries from each benchmark family
TPCH_SF=1 TPCDS_SF=1 OY_THREADS=4 \
bash auto_test/experiment_onoff.sh \
  --only bench --pattern '*_agg[01]' --limit 6 --runs 1

# Full TPC-H family
bash auto_test/experiment_onoff.sh --only tpch

# Force one valid OuterYan candidate for a bare-query correctness comparison
DUCKDB_OY_FORCE_CANDIDATE=1 \
bash auto_test/experiment_onoff.sh \
  --only tpcds --pattern 'oy_ds_ds_bushy5b_v0' --capture-plans

# Skip JOB bushy-7 labels
bash auto_test/experiment_onoff.sh --only bench --exclude '*jb_bushy7*'

# P0/P1 representative run using existing databases
OY_CORPUS=auto_test/outerjoin_query_old \
SKIP_DATA=1 OY_THREAD_COUNTS="16 32" OY_RUNS=3 bash auto_test/run_all.sh \
  --only all --query-list auto_test/representative_queries.txt --capture-plans
```

The release build enables TPCH and TPCDS but does not build HTTPFS.
None of the four benchmark builders requires HTTPFS: network downloads use the
`curl` executable and JOB reads cached local Parquet. Build HTTPFS separately
only on hosts with compatible libcurl development headers.

The scale variables in the second example describe the prepared databases in
the report header; rebuild the databases first if they are not already SF1.

## Output

Without `--out`, one start timestamp identifies the run. For each requested
thread count `N` (only `32` by default), the result group is:

```text
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.txt
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.csv
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.attempts.csv
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.plans/
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.profiles/
```

`run_all.sh` includes the corpus label, for example
`experiment_onoff_benchmark_YYYYMMDD_HHMMSS_t16.csv` and
`experiment_onoff_benchmark_YYYYMMDD_HHMMSS_t32.csv`.

With `--out path/name.txt`, a sweep writes `path/name_t16.txt` and
`path/name_t32.txt`, with matching CSV names. For a single configuration the
explicit output path is used unchanged. Each CSV contains one row per query
and records `timing_threads`, `tm_off`, `tm_on`, and `tm_speedup`. New outputs
contain no `t1_*` columns. Appended `profile_*` columns record status, actual
thread count, R1/R2/R3 operator work and counts, Other CPU work, wall latency,
total CPU work, phase shares, sample count, and the raw profile directory.
When profiling is disabled or skipped, phase measurements remain unavailable.
Each profiled query has its own subdirectory with `profile_0.json` (warm-up),
`profile_1.json` through `profile_N.json`, and `duckdb.log`. The historical
attempts CSV is retained for downstream compatibility and is an identical
single-attempt copy; timed-out queries are not retried.

Live stderr and the TXT report use one clearly separated block per query:

```text
====================================================================================================
[ 63/185] derived__example  correct=TRUE reorder=1 selected=OUTERYAN kernel=bitmap(b=3,h=0) threads=16 TM:off=12.000000000 on=6.000000000 spd=2.000
  details: family=tpch sql=... pass=main timeout=900s note=OK ... decision=[mode=FORCE_OUTERYAN reason=FORCE_OUTERYAN ...] cost=[...] SJ=[R1(... pairs=0 filters=0) R2(... pairs=3 filters=3) ...]
```

The record always uses two lines: line 1 contains the high-level result,
kernel choice, thread count, and timing; line 2 contains decision/cost metadata
and `profile=[status=... threads=... Total-Time=... CPU-Time=... R1=... R2=... R3=... OtherCPU=...]`.
Applicable queries include the OuterYan and
DuckDB cost formula, gate comparison, and join/SJ weights on line 2. With plan
capture enabled, that line also lists the DuckDB-OFF and enabled EXPLAIN files,
full trace, and per-join/per-SJ cost records.

`pairs` counts planned semi-join applications in that round. `filters` counts
new filter constructions; a reused filter contributes another pair without
another filter. These are optimizer plan counts, not profile measurements.

Each query block includes:

| Field | Meaning |
|---|---|
| Line 1 | Query/result, selected plan, kernel counts, thread count, and unprofiled OFF/ON timing and speed-up |
| Line 2 | Family/path/pass, decision mode, cost/gate operands, SJ work, weights, profile status/measurements, hash notices, and optional artifacts |

Each applicable, costed query includes raw cost components and an expanded
gate:

```text
gate formula: candidate_join + semijoin_ratio * semijoin_raw <= baseline_ratio * baseline
gate values:  <join> + <sj-ratio> * <raw-sj> <= <baseline-ratio> * <baseline>
gate result:  <candidate-total> <= <threshold> => PASS|FAIL -> <decision>
```

For same-grouping, inapplicable, unavailable, or forced-policy cases, the report
states that the numeric gate was skipped and prints the decision reason.

The CSV exports the same decision, cost, kernel, correctness, and timing
fields in machine-readable form, including the SQL-derived `relation_count`,
`default_filter_upper_bound_checked`, `default_filter_upper_bound_selected`,
`full_reduction_cardinality_lower_bound_applied`,
`uncertain_filter_amplification_guard`,
`stretch_cost_gate_eligible`, `stretch_cost_gate_selected`,
`baseline_join_input_rows`, `candidate_join_input_rows`,
`candidate_to_baseline_join_input_ratio`,
`semijoin_retained_cardinality_ratio`,
`uncertain_filter_cardinality_amplification`, `round1_pairs`,
`round1_filters`, `round2_pairs`, and `round2_filters`.
`effective_pass` remains `main` for schema compatibility. The final text summary groups speed-ups separately by
`outer_reordered` and `outer_yan_selected`, and reports query, correct, and timed
counts for every relation depth present in the run.

`plot_speedup.py` writes one multi-page `outeryan_benchmark_figures.pdf` by
default, with optional standalone figures. Files with the same timestamp and
thread suffix are merged into one logical run; `_t16` and `_t32` are never
merged. Historical `core` and `industry_inspired` CSV pairs remain supported.
The all-query figure is one shared speed-up scatter axis. Every correct query
with finite, positive OFF/ON timings contributes one point; the y-value is
`OFF / ON` on a logarithmic scale. Each benchmark occupies a separate x-axis
region, subdivided by query-name shape/category (not join-graph topology). Points have 50% opacity and
deterministic horizontal jitter within their shape slot, so overlaps show
density without changing speed-up values. The enlarged benchmark legend is one
horizontal row above the axes. Query names are omitted. The dashed line is `1x`;
this figure is not sampled.

One `Running time Comparison` figure combines graph, TPC-H, TPC-DS, and JOB.
By default, `--representative-scope outeryan` samples only correct queries whose
ON run selected OuterYan, including regressions, with complete timing pairs.
Use `--representative-scope all` for the optional all-plan view.
Each family targets `--representatives-per-benchmark`
(default 15); a family with fewer eligible queries is shown in full, without
reducing the other families' quotas. Within each family, slots are allocated round-robin over
available shapes, retaining every shape when the quota permits. Within a shape,
queries are ordered by DuckDB OFF time and sampled at evenly spaced ranks (the
middle rank for a single slot). Sampling does not rank speed-up or ON time.
A family with no eligible queries cannot be represented; no measurements are
invented to fill its quota. In the all-plan view, an asterisk after a query ID
means the recorded ON plan selected OuterYan; an unmarked ID means DuckDB was
selected. A question mark identifies an unavailable plan rather than assuming
DuckDB. The ON legend reads "OuterYan enabled", which does not imply every ON
run selected an OuterYan plan. Sampling does not rank or favor plan selection.

Each new multi-thread-only query has two contiguous OFF/ON bars. Historical result
files with both thread settings retain their four-bar comparisons, using blue
and peach pairs. Only queries with complete finite, positive timings for their
result schema are included; incomplete queries are omitted. Query IDs are
assigned from the full in-scope population before this filtering so the
remaining labels do not change. IDs can differ between the all-plan and
OuterYan-only scopes; the adjacent JSON manifest provides the exact mapping.
Benchmark subtitles and separators identify the sections. Query labels and
legends are enlarged, with the abbreviation key directly below the `Query` axis.
The shape parser recognizes the generated `bdmx`, `bmx`, `ldmx`, `rdax`,
`rdmx`, `rduX`, and `alt` suffixes, plus `lduX` in historical result files.
There is intentionally no
speed-up-by-kernel page.

When profiles exist, the default OuterYan-selected runtime comparison and
`OuterYan Execution Time Details` share one sample, short-ID mapping and order.
Only queries with complete profile data and a same-run, matching-thread OFF
baseline are eligible for that paired view. All samples
share one vertical grouped-bar axis with benchmark subtitles and separators.
Each query has `Round 1`, `Round 2`, `Round 3`, residual `Other`, and profiled
wall-clock `Total Time`, plus `Baseline Time` (unprofiled DuckDB OFF median)
bars on a base-10 logarithmic y-axis. DuckDB-selected
queries and incomplete profiles are omitted rather than represented as zero.
The phase and `Other` values are aggregate operator CPU work across threads,
while `Total Time` is wall-clock time; the bars are not an additive wall-time
decomposition.

The compact representative figures label queries as
`<benchmark>-<shape>-<index>`: `G/H/D/J` are graph/TPC-H/TPC-DS/JOB and
`LD/RD/B/S/A/I/O` are left-deep/right-deep/bushy/star/aggregate/industry/other.

Pass `--split-output-dir DIR` to additionally write `speedup_all_queries.pdf`
and the merged `runtime_outeryan_queries.pdf` (or
`runtime_representative_queries.pdf` with `--representative-scope all`). The sampled full query names,
short labels, shapes, available family counts, and timings are recorded in
`representative_queries.json`.
`phase_breakdown_outeryan.pdf` is written only
when eligible profile data exists. With multiple logical runs, each run is
written under its timestamp subdirectory.

Keep the current 0908 figure set, previews, manifests, and statistics together
in `results/plots/20260908_235240/t32/`; `FIGURE.md` there is the gallery.
Do not create separate `sample` or `balanced` output directories. That 0908 run
has no profiles. To reproduce its temporary breakdown, explicitly add
`--phase-placeholder-csv results/experiment_onoff_benchmark_20260830_002656.csv
results/experiment_onoff_benchmark_20260830_002656.attempts.csv` when invoking
the plot script from `auto_test/`. This input is used only for the breakdown,
is visibly labeled with its old date and actual 48-thread count, and never
enters current timing or statistics. `phase_queries.json` records the exact
profile samples and placeholder status. When current complete profiles exist,
they take precedence and the placeholder label disappears; omit the legacy
flag when regenerating from the new server run.

Complete descriptive statistics are also exported as `STATISTICS.md` and
`statistics.json`, in the split output directory when provided, otherwise in
`<output-PDF-stem>_statistics/`. Use `--statistics-dir DIR` to override this.
Statistics use the full deduplicated run, not the representative sample, and
report all queries, OuterYan-selected queries, and DuckDB-selected queries
separately. Each population has overall, benchmark, shape, and benchmark-by-shape
groups. Outputs include min/max with query names, arithmetic/geometric means,
median, P05/P10/P25/P75/P90/P95/P99, sample SD/variance (ddof=1), coefficient of
variation, faster/equal/slower counts, ratio bands, paired OFF/ON runtime
distributions and totals, total-time speed-up, and saved time. Source paths,
SHA-256 fingerprints, all per-query timing pairs, and exclusion reasons are
included in JSON. Markdown displays six decimals; JSON retains calculation precision.
Timeouts and incomplete/incorrect observations are counted but never imputed.
These are query-population descriptions, not confidence intervals from repeated
runs. Shape uses the existing query-name classification, not the optimized physical plan.

Result files are grouped by their filename timestamp before plotting. A paired
`experiment_onoff_<timestamp>.csv` and
`experiment_onoff_<timestamp>.attempts.csv` therefore produce one figure set,
not two runs. Duplicate `(family, query)` rows use the final CSV value; an
attempts row is retained only when the final CSV is missing, empty, or lacks
that query. This preserves partial interrupted runs without double-counting the
compatibility copy. Component names do not create separate logical runs when
their timestamps match.

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
| `outer_yan_bitmap_max_bytes` | 32 GiB per filter | Bitmap budget; `0` forces hash |
| `outer_yan_hash_fn` | `duckdb` | Hash implementation; alternative is `murmur` |
| `outer_yan_stats_prefilter` | `false` | Use base min/max statistics to skip unsuitable bitmap attempts |
| `DUCKDB_SJ_KERNEL_TRACE` | unset | Emit finalized bitmap/hash kernel records |

Set session controls with DuckDB variables, for example:

```sql
SET VARIABLE outer_yan_bitmap_max_bytes = 0;
SET VARIABLE outer_yan_hash_fn = 'murmur';
SET VARIABLE outer_yan_stats_prefilter = true;
```

Kernel output uses `not-run`, `bitmap(b=N,h=0)`, `hash(b=0,h=N)`,
`mixed(b=N,h=M)`, or `none(b=0,h=0)`. Hash and mixed results also report
reason counts. Raising the bitmap budget can address `overflow` (and
`force_hash` after replanning), but not `ineligible` key types or composite
keys.

Disable the cohesive optimizer with:

```sql
SET disabled_optimizers TO 'outer_yan';
```

## One-command and manual workflows

```bash
# Build release and data, regenerate queries, then compare DuckDB Original and
# OuterYan for every query in auto_test/outerjoin_query. No PG plan is generated
# or executed by this default workflow.
bash auto_test/run_all.sh

# Explicitly opt into PGPlan generation and Original/PGPlan/OuterYan testing.
RUN_PGPLAN=1 bash auto_test/run_all.sh

# Check only (a) Original == PGPlan; OuterYan correctness is skipped, while
# Original/PGPlan/OuterYan EXPLAIN and performance remain unchanged.
RUN_PGPLAN=1 bash auto_test/run_all.sh --skip1

# Skip both correctness comparisons for a manual performance-only rerun.
# Cached PGPlan artifacts are reused; all EXPLAIN, verification, and TM
# performance work still runs.
RUN_PGPLAN=1 bash auto_test/run_all.sh --performance-only

# Optionally use the pinned postgres:16.2 image instead of the default
# repo-local source build.
RUN_PGPLAN=1 PGPLAN_SETUP=docker bash auto_test/run_all.sh

# Use an existing PostgreSQL 16.2 instance. Its public schema must contain
# exact TPC-H SF0.01, and the role must be able to create sampled schemas.
PGPLAN_SETUP=external \
PG_DSN='host=127.0.0.1 port=5432 dbname=duckyan_tpch user=postgres' \
PSQL_BIN=/absolute/path/to/psql \
RUN_PGPLAN=1 bash auto_test/run_all.sh

# Reuse existing DuckDB data; setup still verifies or prepares PostgreSQL's
# independent minimal plan-selection data. Run only the TPC-H family.
RUN_PGPLAN=1 SKIP_BUILD=1 SKIP_DATA=1 bash auto_test/run_all.sh --only tpch

# Performance rerun: reuse each query's PGPlan artifact and sealed target-data
# correctness receipt. PostgreSQL setup/capture and result comparison are
# skipped; Native, PGPlan, and OuterYan EXPLAIN/TM tests are otherwise the
# same and are written to a new self-contained result directory.
RUN_PGPLAN=1 bash auto_test/run_all.sh \
  --reuse-from /absolute/path/to/prior/pgplan_corpus_YYYYMMDD_HHMMSS

# The explicit spelling below is equivalent to the default two-way workflow.
RUN_PGPLAN=0 bash auto_test/run_all.sh

# Run PGPlan on another family-structured corpus root.
RUN_PGPLAN=1 PGPLAN_CORPUS=auto_test/outerjoin_benchmark/core \
  SKIP_BUILD=1 SKIP_DATA=1 bash auto_test/run_all.sh --only bench

# Run one custom corpus through the default two-way harness.
OY_CORPUS=auto_test/outerjoin_benchmark/core \
  SKIP_BUILD=1 SKIP_DATA=1 bash auto_test/run_all.sh --only bench
```

The default comparison stage walks all 176 SQL files under `outerjoin_query`:
7 graph, 53 TPC-H, 43 TPC-DS, and 82 JOB queries. It executes each bare query
with OuterYan disabled (Original) and enabled, verifies complete result
equivalence, records the selected DuckDB/OuterYan plan, and then measures both
configurations. It does not inspect the PGPlan cache, start PostgreSQL, capture
PG plans, import PG plans, or run PGPlan correctness/timing.

With `RUN_PGPLAN=1`, the opt-in comparison instead checks the persistent typed-
plan cache under `auto_test/pgplan/plans`, captures missing or stale PostgreSQL
artifacts, and runs the Original/PGPlan/OuterYan workflow.
PostgreSQL is a planning oracle only: it receives plain `EXPLAIN`,
never `EXPLAIN ANALYZE` and never a result-producing execution.
`--only`, `--pattern`, and `--limit` select a smaller fail-closed run. Every
attempt is recorded in `status.tsv`; there is no native-plan fallback when
capture or PGPlan application fails. A PostgreSQL planning, DuckDB execution,
or correctness post-processing timeout is recorded as `SKIP` and the next
query continues. Both `SKIP` and `FAIL` make the corpus command return nonzero,
so a successful run means every selected query completed correctness and both
timing suites. For a quicker diagnostic without a target-scale correctness
claim, set `PGPLAN_CORRECTNESS_MODE=bounded`.

Override the plan cache with `PGPLAN_PLAN_CACHE` or `--plan-cache`. A cached
entry must match the exact canonical query hash, artifact SHA-256, PostgreSQL
version/settings, family schema/data identity, bounded planning-sample
fingerprint, statistics epoch, and typed binary tree. Otherwise every selected
query in that family is recaptured under one coherent `ANALYZE` epoch and
replaced atomically. `--skip1` selects only Original-versus-PGPlan correctness.
`--performance-only` (aliases: `--skip2`, `--performance_only`, and the accepted
misspelling `--performace_only`) skips both result comparisons but retains all
plan verification and performance phases. Its correctness status is honestly
recorded as `NOT_RUN`.

For repeat performance measurements, `--reuse-from PRIOR_CORPUS` verifies and
reuses the prior target-scale correctness receipt and PGPlan artifact for the
same family/query. It skips PostgreSQL setup, sampled-schema preparation, plan
capture, and new CSV export/sort/comparison. Reuse is cryptographically bound
to the exact query bytes, PostgreSQL artifact, DuckDB binary/version, and
target database. A default complete target-correctness run and a sealed reuse
run fingerprint each selected target database once. `skip1` and
performance-only avoid that full-file read because they cannot create or
consume a complete correctness receipt. Every mode still rejects a non-empty
or unsafe DuckDB `.wal`; a missing receipt/artifact, hash mismatch, or path
escaping the prior root is a per-query failure with no fresh-correctness or
native-plan fallback. Remaining queries continue.
`PGPLAN_CORRECTNESS_MODE=reuse` plus `PGPLAN_CORRECTNESS_FROM` remains the
granular option when only correctness should be reused and fresh PostgreSQL
plans are still desired.

This is one comparison workflow with three timed configurations: Original,
PGPlan, and OuterYan. Each successful query writes its TM medians under
`runs/<family>/<query>/timing/summary.tsv`; no single-thread batch is run.
`run_all.sh` runs the three-way corpus at 32 threads by default. An explicit
`--threads "16 32"` sweep creates separate `_t16` / `_t32` output directories.
A correctness-reuse receipt is thread-specific:
use `--threads N` matching the source run when using `--reuse-from`.
At corpus completion the runner also writes `comparison.tsv` and
`comparison.csv` with one row for every selected query, a human-readable
`comparison.log`, `summary.tsv` with all-family and per-family aggregate
counts/speedups, and `failures.tsv` with every incomplete query and its
phase/reason. During a normal corpus run, each terminal PASS/FAIL/SKIP is
immediately streamed as a legacy-style, separator-delimited query block; the
same blocks are retained in `comparison.log` beside the tabular reports. Its
rows and values come from the same ordered comparison records as the TSV and
CSV, so the screen-readable and machine-readable reports stay in parity.
Timing and speedup fields are populated only for `PASS` rows.

The comparison CSV/TSV starts with the `experiment_onoff.sh` decision/timing
header prefix (excluding its appended `profile_*` fields), in its original
order and with unchanged meanings. Appended fields are all
identified by `pgplan` in their names and cover PGPlan verification/timing,
comparison mode/status, and correctness provenance. Raw plan signatures remain in trace artifacts;
they are not printed in the human log or copied into the CSV.

The provenance columns distinguish `FRESH`, `PARTIAL`, `NOT_RUN`, and `REUSED`
correctness. Reused rows retain their source/receipt hashes; legacy artifacts
leave unavailable additive fields empty instead of guessing.

Each successful block orders TM as Original, PGPlan, OuterYan, then
prints only `Original/OuterYan` and `PGPlan/OuterYan` speedups. The original
CSV `off/on` columns retain their Original/OuterYan meanings, while
`tm_pgplan` adds PGPlan; legacy Original/PGPlan speedup fields remain for
compatibility. TM uses one warm-up plus `PGPLAN_RUNS` measurements. No
single-thread or phase-profile columns are emitted for new runs. When
re-summarizing historical runs with a real `timing/t1_summary.tsv`, the report
appends their `t1_*` fields and retains the corresponding human-log values.
The workflow does not collect the legacy kernel-trace batch; its CSV kernel
fields remain unavailable. Its
original `rows` column is the complete target-scale result count by default. These
reports are generated before a failure status is returned, so a mixed run
remains inspectable without rerunning completed queries.

An already completed corpus directory can be summarized without executing any
query again:

```sh
bash auto_test/pgplan/summarize_corpus.sh \
  --result-dir /absolute/path/to/pgplan_corpus_YYYYMMDD_HHMMSS
```

That command regenerates `comparison.log`; use `less` or `cat` to display it.
It does not recapture a PostgreSQL plan or repeat correctness or timing
executions.

The workflow deliberately separates PostgreSQL plan-selection data from the
DuckDB target data:

1. PostgreSQL plan selection uses exact TPC-H SF0.01 or isolated graph,
   TPC-DS, and JOB schemas capped by `PGPLAN_SAMPLE_ROWS` (1000 rows per table
   by default), followed by `ANALYZE`. These rows select the typed logical tree
   through plain `EXPLAIN` only.
2. The configured target DuckDB files are used for both requested multiset
comparisons, all three EXPLAIN plans, PGPlan semantic-signature verification,
   and release timing. Correctness emits complete CSV and sorts it externally.
   Timing uses `.mode trash`, which still executes and fully drains the bare
   query while excluding CLI CSV serialization and filesystem output from the
   DuckDB CLI's real wall-clock sample.

`PGPLAN_CORRECTNESS_MODE=bounded` is an explicit diagnostic alternative. It
builds deterministic small correctness databases and records their
fingerprints, but its PASS is scoped only to that bounded data.

Reuse does not make a new correctness claim: a reuse-mode PASS cites a sealed
prior target-mode equality check whose fingerprints match the current inputs,
then reruns all three plan verification and timing configurations. The new
result copies the selected PGPlan artifact and receipt provenance so it does
not depend on mutable files in the prior result directory after completion.

Accordingly, a target-mode PGPlan PASS supports exact target-data
Native/PGPlan/OuterYan result equality, PGPlan tree adherence, and target-data
performance. It still does not represent execution of PostgreSQL's physical
plan. See [`pgplan/README.md`](pgplan/README.md) for the manual
`--correctness-db` interface and builder options.

`PGPLAN_SETUP=source` follows the repo-local paths in `configs.sh` and pins
PostgreSQL 16.2. If the managed binary is absent, it downloads the verified
official source, builds and installs it, initializes a repo-local cluster, and
starts it on the configured loopback endpoint. It deliberately does not depend
on detecting a system PostgreSQL installation. Docker is optional; `docker`
uses the pinned container, while `external` requires the caller's `PG_DSN` and
`PSQL_BIN`. Both managed modes generate and reuse a private mode-`0600` secret
unless a password is explicitly provided. An older Docker container with a
different credential fails with instructions to recreate it or provide its
current password. See
[`pgplan/README.md`](pgplan/README.md) for the manual capture
and PGPlan experiment workflow. External mode requires
`PGPLAN_FORCE_SAMPLED_DATA=1` before replacing an existing graph, TPC-DS, or JOB
sample schema. Existing `PG_REPLAY_*` environment names remain
accepted only as compatibility aliases, but new commands and result labels use
`PGPLAN_*` and `pgplan`.

Manual equivalent for the unified two-way benchmark stage:

```bash
BUILD_TPCH=1 BUILD_TPCDS=1 GEN=ninja make release
bash auto_test/build_db.sh all
python3 auto_test/gen_outerjoin_benchmark.py
OY_CORPUS=auto_test/outerjoin_query \
  bash auto_test/experiment_onoff.sh --only all
```

`run_all.sh` and `build_db.sh` reuse existing database files. If a requested
scale or graph differs from the database already on disk, rebuild that database
explicitly with `FORCE=1` before running the experiment.
