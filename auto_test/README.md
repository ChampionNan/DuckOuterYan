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
| `outerjoin_benchmark/` | Canonical mixed v1 view, expanded v2 selectivity workload, 102-query v3 aggregation workload, manifests, and paper text |
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
| `OY_PROFILE` | `1` | One post-warm-up OFF/ON execution profile for optimizer totals; the same ON sample supplies phase breakdown when OuterYan is selected |
| `OY_CAPTURE_PLANS` | `0` | Save OFF/ON EXPLAIN, optimizer trace, and cost-step artifacts |
| `OY_CORPUS` | `auto_test/outerjoin_benchmark/benchmark` | Canonical v1 corpus root |
| `OY_CORPUS_SCOPE` | `benchmark` | Versioned view: v2 has `job-regressions`; v3 has `selectivity-stress` |
| `RUN_PGPLAN` | `0` | Set to `1` to opt into PGPlan generation and three-way comparison |
| `PGPLAN_SETUP` | `source` | PostgreSQL provider: repo-local source build, Docker, or an external DSN |
| `PGPLAN_SOURCE_DIR` | `postgres` | Repo-local PostgreSQL source/build root used by `source` mode |
| `PGPLAN_INSTALL_DIR` | `postgres/postgresql` | Repo-local PostgreSQL installation prefix used by `source` mode |
| `PGPLAN_PASSWORD_FILE` | `postgres/postgresql/.pgplan-password` | Mode-`0600` generated secret for managed source and Docker servers |
| `PGPLAN_CORPUS` | `auto_test/outerjoin_benchmark/benchmark` | Corpus whose selected queries receive validated cached or freshly captured PGPlan artifacts |
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

The canonical v1 corpus is **v1-mixed**
(`corpus_revision=v1-mixed-graph25-20260925`), the 224-query workload under
`outerjoin_benchmark/benchmark/`. It contains all 170 source-derived structures
and all 54 Graph/industry/schema-synthetic evaluation controls.
The retired FULL-heavy v1 timeout hashes do not filter this corpus: changing
join labels changes the SQL and invalidates both the old timing and timeout
observations. `active_timeout_exclusions.csv` is therefore empty. Historical
exclusions remain documented in `benchmark_timeouts.py` and
[`active_corpus_coverage.md`](outerjoin_benchmark/active_corpus_coverage.md),
but must not be interpreted as measurements of the current revision.
Labels are SQL basenames without `.sql`; `--pattern` and `--exclude` match the
entire label using shell-glob syntax.

```bash
# Regenerate or test v1 only.
python3 auto_test/gen_outerjoin_benchmark.py
bash auto_test/experiment_onoff.sh --version v1 --only all

# Generate and test the 564-query expanded v2 corpus.
python3 auto_test/gen_outerjoin_benchmark.py --version v2
bash auto_test/experiment_onoff.sh --version v2 --only all

# Generate v3, then test its 102 aggregation and 42 selectivity-stress queries.
python3 auto_test/gen_outerjoin_benchmark.py --version v3
bash auto_test/experiment_onoff.sh --version v3 --only all

# Aggregation component only.
bash auto_test/experiment_onoff.sh --version v3 --corpus-scope benchmark --only all

# Default: run all benchmark versions plus v3 selectivity-stress sequentially.
bash auto_test/experiment_onoff.sh --all
# The following is equivalent:
bash auto_test/experiment_onoff.sh

# Metadata-selected balanced selectivity ablation; report separately.
bash auto_test/experiment_onoff.sh --version v3 \
  --corpus-scope selectivity-stress --only all

# Reproduce the two confirmed JOB regressions only.
bash auto_test/experiment_onoff.sh --version v2 \
  --corpus-scope job-regressions --only job
```

Version selection is therefore unambiguous: `--version v1`, `--version v2`,
and `--version v3` run exactly that version (v3 includes both of its scopes
unless `--corpus-scope` narrows it); `--all` runs v1, v2, v3 aggregation, and
v3 selectivity stress: 224 + 564 + 102 + 42 = 932 query instances. With no
version option, the harness behaves exactly as `--all`.

V2 is stored under `outerjoin_benchmark/v2/` and does not replace v1. It applies
three bounded deterministic selectivity tiers (approximately 0.1%, 1%, and 5%)
to 170 source-derived structures, then adds the 54 v1 evaluation controls. Both
v1 and v2 use the same mixed-join design. Every
source seed still contributes the same five graph-preserving shapes, but their
join edges use a deterministic cyclic assignment of `I/L/R/F`. Across the 170
base structures, the 625 join edges contain 157 INNER and 156 each LEFT,
RIGHT, and FULL labels. The three selectivity copies retain the same vector for
each base. The 54 Graph, industry, and schema-synthetic controls are retained,
but their existing relations, predicates, and grouping are relabeled with the
same balancing rule. In the complete 224-query v1 union, the 801 edge
occurrences contain 200 INNER, 201 LEFT, 200 RIGHT, and 200 FULL labels.
Consequently, the complete 564-query v2 main workload has
512 INNER, 513 LEFT, 513 RIGHT, and 513 FULL edge occurrences. It includes 75
all-outer queries (using two or more of LEFT/RIGHT/FULL) and 489 queries that
also contain INNER; no v2 main query has a single-kind vector such as all-FULL.
These are input-expression labels; optimizer simplification and physical join
selection are measured outcomes, not part of the corpus-balancing rule.

The 170 structural bases remain traceable to 34 source queries from TPC-H,
TPC-DS, JOB, and SQLStorm. Their relation instances and equality-edge graph are
retained. Graph and industry/schema-synthetic queries are explicitly labeled
as control strata in `benchmark/manifest.csv`, rather than being presented as
source-derived benchmark queries. The manifest also records which strata are
motivated by the 0916 advantage hypothesis, but all seeds, shapes, join-label
rotations, and paired controls remain included independently of measured speed. See
`outerjoin_benchmark/README.md` for the design and provenance fields.

The generated `v3/selectivity_stress/` directory contains 42 variants of six
metadata-selected mixed v2 counterparts of feasibility-screened v1 structures
at approximately 0.025%, 0.05%, 0.2%, 10%,
20%, 50%, and 80% target selectivity. The ablation domain is declared from
static metadata: mixed joins with at least four relations and an applicable
null-rejecting predicate. Two distinct source queries are selected from each
of TPC-H, TPC-DS, and JOB; across the complete set there are two left-deep, two
right-deep, and two bushy structures. Each family contributes one native
benchmark source and one SQLStorm-derived source. Selection uses fixed family/shape/source slots
and a salted SHA-256 rank over query identifiers and never reads measured
runtimes. Every tier contains six queries
and uses a common deterministic 4,000-bucket hash sample. This is equal
representation per tier, not a claim of numerically uniform or realized
selectivity. The manifest records `performance_selected=false` and marks every
query `headline_eligible=false`; keep this correlated selectivity ablation
separate from headline scores.

The v3 aggregation component contains 102 queries: 42 global `COUNT(*)`, 30
grouped `SUM`, 15 grouped `MIN`, and 15 grouped `MAX`. MIN and MAX split one
extremum class equally. Each of the three structural slots receives exactly 14
COUNT, 10 SUM, 5 MIN, and 5 MAX assignments from a static weighted schedule;
the assignment never reads experimental results.
The separate `v2/job_regressions/` directory contains the mixed-v2 counterparts
of two historical FULL-heavy v1 JOB cases below 0.95x. Their structure remains in the
main benchmark so difficult cases are not silently removed. Because changing
join labels changes the query, the old v1 speedups are provenance only; both
v2 counterparts are marked `requires_v2_remeasurement`.

Generation is deterministic and writes query-level provenance manifests. Active
query names use only `derived__` and `industry__`. The benchmark-derived core
has 170 queries (TPC-H 25,
TPC-DS 35, JOB 50, and SQLStorm 60), including 46 left-deep, 80 right-deep,
and 44 genuinely bushy graph-preserving applicability inputs. Its 625 join
edges contain 157 INNER and 156 each LEFT, RIGHT, and FULL. The 54-query
evaluation component contains nine explainable business-role patterns, all 25
completed Graph-generator patterns, and 20 schema-synthetic regression guards.
The complete Graph set is included without consulting performance; seven rows
retain historical speed-up only as provenance. The 25 Graph structures comprise
10 bushy, seven left-deep, and eight right-deep expressions. The active
224-query union contains the 170-query core plus all 54 controls.
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
`benchmark_timeouts.py` now documents only the retired FULL-heavy revision.
The current active view applies none of those exclusions; any timeout policy
must be rebuilt from a completed mixed-v1 run and pinned under a new revision.

Query traversal is deterministic. Families are visited in the order selected by
the harness; `--only bench` means `tpch`, then `tpcds`, then `job`. Within each
family, SQL basenames are ordered bytewise (`LC_ALL=C`). A bushy-eligible seed
emits `bdmx`, `bmx`, `ldmx`, `rdmx`, and `rduX`; a bushy-ineligible seed emits
`alt`, `ldmx`, `rdax`, `rdmx`, and `rduX`. Here `X` is a legacy filename label;
this is only filename order, not a semantic progression. A `--query-list` file
overrides this order and is processed line by line.

### Mixed v1/v2 core query variants

The suffix records the binary join-tree traversal and remains stable for result
continuity; it does not encode the join vector. Both current corpus versions
assign every shape a deterministic mixed vector. For a query with four or more
join edges, the vector contains all four join kinds; shorter queries contain
consecutive two- or three-kind slices of the `I/L/R/F` cycle. This produces both
all-outer (`L/R/F`) queries and queries that mix INNER with outer joins while
keeping aggregate edge frequencies balanced. The manifest's `join_vector` is
authoritative.

| Suffix | Tree and join labeling | Meaning |
|---|---|---|
| `ldmx` | Primary left-deep mixed tree | Primary left-deep traversal of the fixed graph. |
| `rdmx` | Primary right-deep mixed tree | Primary right-deep traversal of the fixed graph. |
| `bmx` | Connected bushy mixed tree | Tests bushy grouping without a cross product; emitted only when both root subtrees can contain at least two relations. |
| `bdmx` | Secondary connected bushy mixed tree | Uses another connected split/orientation of the same fixed graph. |
| `alt` | Alternate left-deep mixed tree | Replaces `bmx` when a true cross-product-free bushy tree is unavailable. |
| `rdax` | Secondary right-deep mixed tree | Replaces `bdmx` when the graph cannot form a true bushy root. |
| `rduX` | Alternate right-deep mixed tree | Starts at the opposite graph side; `X` is a legacy filename label and does not override the manifest vector. |

The core contains 46 left-deep, 80 right-deep, and 44 bushy queries. Every
grouping is independently specified because outer joins are not generally
associative. Every input contains at least two join kinds and at least one outer
join. Global NULL-rejecting predicates remain selective, while the mixed
vectors exercise both simplification and applicability boundaries.
The two historical aggregate patterns in the active evaluation set are emitted
as detail projections so they do not bypass OuterYan.

Twenty schema-synthetic legacy regression guards remain explicitly labeled in
the evaluation component. Other historical queries stay in
`outerjoin_query_old/` as generation/provenance inputs.

## Experiment pipeline

`experiment_onoff.sh` and `run_all.sh` use **32 threads only** by default.
Request a sequential sweep explicitly with `--threads "16 32"` or
`OY_THREAD_COUNTS="16 32"`; each configuration uses separate processes and
output files. Use `--threads 16` / `OY_THREADS=16` for a different single
configuration. Thread counts must be greater than one; CLI settings take
precedence. Database setup and query generation in `run_all.sh` happen only
once before any requested sweep.

For every selected query at each thread count, `experiment_onoff.sh` performs:

1. Run a traced `EXPLAIN` in a fresh process and read one `[OY_DECISION]` record,
   including `aggregate_query`, `aggregate_pushdown_applied`, and `selected_plan`.
2. Execute a query only when it selects OuterYan and, for an aggregate query,
   the selected plan actually contains at least one aggregate pushdown. A DuckDB
   fallback or an aggregate query without a realized pushdown is retained as
   `note=FALLBACK-SKIP`, `timing_status=fallback-skip`, with unavailable OFF/ON
   runtimes and the selection-policy speed-up default `1.0`. For remaining
   queries, execute the bare query with OuterYan OFF and ON, sort the emitted CSV
   files outside DuckDB, and compare the result multisets. A mismatch, error, or
   timeout is not timed. No SQL wrapper changes the optimized plan.
3. If OuterYan was selected, run one kernel-classification execution and record
   bitmap/hash filter counts.
4. Time OuterYan OFF and ON at `threads=$OY_THREADS`. Each batch
   has one warm-up followed by `--runs N` timed executions; the median excludes
   the warm-up.
5. For every executed correct query, execute OFF and ON once after one unprofiled warm-up
   while collecting a detailed JSON profile. DuckDB's `all_optimizers` value is
   the OFF total. The ON total adds OuterYan's cost-model phase because that
   phase sits between named DuckDB optimizer timers and is therefore absent
   from `all_optimizers`. The ON record also exports the algorithmic
   OuterYan workflow phases: applicability, OT construction, simplification,
   semi-join-pair planning, desimplification, OuterYan join reorder, DuckDB
   baseline simplification/reorder, cost model, resimplification, aggregate
   marking, plan lowering, semi-join insertion, and aggregate pushdown. Generic
   DuckDB optimizer-pass timings are not reported.
6. For correct queries whose ON plan selects OuterYan, read R1/R2/R3 operator
   work from that same post-warm-up ON execution profile. This is enabled by
   default (`OY_PROFILE=1`); `--no-profile` or `OY_PROFILE=0` skips both optimizer
   and phase profiling. The performance medians in step 4 remain unprofiled and
   independent of this single diagnostic sample.

Every statement uses the same fixed `OY_TIMEOUT_SECS` limit. The larger external
watchdog on a timing/profile process only accounts for the four fixed-limit
statements in that process; it does not increase any statement's timeout. At the
first timeout in correctness, kernel classification, timing, or profiling, the
query is marked `TIMEOUT-*`, the remaining phases for that query are skipped,
and the query is never retried with a longer limit.

All executions explicitly set the selected multi-thread count. Correctness,
diagnostics, and OFF/ON performance timing disable profiling. There is no
single-thread batch. Timing runs in fresh `-no-init` CLI processes using `.mode
trash`, which fully drains the bare query without measuring CSV formatting or
file output. Correctness and optional plan/cost diagnostics remain enabled.
Profile work adds one paired OFF/ON execution batch and never contributes
to OFF/ON timing medians or speed-up. A profile failure leaves valid timing pairs
intact. Optimizer and phase failures are recorded independently as
`OPTIMIZER-PROFILE-ERROR` and `PROFILE-ERROR`; partial JSON files and CLI logs
remain available for diagnosis.

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

Cost formula V9 retains two consistency checks before that final comparison.
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

Cost formula V9 uses the full modeled semi-join row-work (`1.0 *
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

V9 also exposes a separate stats-backed unary-filter tier. Let `s` be the
minimum filtered/base cardinality ratio among pre-join base scans. A predicate
retained at root scope is not credited because it does not reduce join or
semi-join inputs. If `s <= 0.35`,
the estimate did not use DuckDB's generic filter fallback, the confidence
guards above are clear, `candidate_join_cost < baseline_cost`, and the
candidate/baseline join-input ratio is at most `0.75`, the gate computes:

```text
progress = (0.35 - s) / 0.35
low_selectivity_limit = strict_ratio_limit
                        + progress * (1.20 - strict_ratio_limit)
```

The final relaxed limit is the maximum applicable tier. This is continuous at
`0.35`: the threshold itself receives no discontinuous bonus, while lower
selectivity makes selection progressively more likely. Generic/default 20%
estimates never qualify. A candidate admitted only by this tier records
`COST_OUTERYAN_LOW_SELECTIVITY`.

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
| `DUCKDB_PLAN` | Candidate has the same grouping as DuckDB; use DuckDB |
| `DUCKDB_PROVEN_EMPTY` | DuckDB's proof copy eliminates all real join work; use DuckDB without SJs |
| `FORCE_OUTERYAN` | Changed candidate selected by the forced experiment mode |
| `FORCE_OUTERYAN_DIAGNOSTIC` | Complete candidate forced past grouping and cost selection for a targeted correctness run |
| `COST_OUTERYAN_BETTER` | Changed candidate passed the configured threshold |
| `COST_OUTERYAN_STRETCH` | High-confidence candidate passed the relaxed `1.20` stretch threshold |
| `COST_OUTERYAN_LOW_SELECTIVITY` | Stats-backed unary selectivity at or below `0.35` admitted the candidate through the continuous low-selectivity tier |
| `COST_DUCKDB_BETTER` | Changed candidate exceeded the configured threshold |
| `COST_UNCERTAIN_FILTER_AMPLIFICATION` | Unknown-selectivity amplification guard rejected the candidate |
| `COST_UNAVAILABLE` | A finite comparison could not be produced |
| `OUTERYAN_FAILED` | OuterYan did not produce a complete candidate |

Supported root aggregate and DISTINCT queries enter the same candidate pipeline.
They use a stricter gate: `candidate_total <= 0.90 * baseline_cost`, with neither
the stretch tier nor the low-selectivity relaxation. The gate deliberately does
not credit estimated aggregate-pushdown benefit. Aggregate pushdown runs only
after this gate selects the OuterYan candidate; a rejected candidate returns the
exact DuckDB baseline without an OuterYan-specific rewrite. Aggregation inside a
join skeleton remains `INAPPLICABLE`. The enabled decomposition paths cover the
v3 grouped `MIN`, `MAX`, and `SUM` queries. Global `COUNT(*)` still participates
in candidate selection and semi-join reduction, but remains above the joins so
outer-join NULL-padding retains exact count semantics.

### Command-line options

```text
bash auto_test/experiment_onoff.sh [options]
  -b, --bin PATH      DuckDB CLI
  -n, --runs N        positive odd timed executions per configuration
  -t, --timeout S     per-statement timeout
      --threads LIST  multi-thread counts (default "32"; also accepts 16,32)
      --version V     run exactly v1, v2, or v3 (v3 includes both scopes)
      --all           run v1, v2, v3 aggregation, and v3 selectivity-stress (default)
      --corpus-scope S  benchmark, v2 job-regressions, or v3 selectivity-stress
      --only FAMILY   select|agg|pred|graph|tpch|tpcds|job|bench|all
      --pattern GLOB  include matching labels
      --exclude GLOB  exclude matching labels; separate globs with |
      --limit N       global query cap; 0 means unlimited
      --query-list FILE  ordered corpus-relative SQL paths; requires --only all
      --capture-plans save OFF/ON EXPLAIN, trace, and detailed cost files
      --profile       enable phase and optimizer profiling (default)
      --no-profile    skip phase and optimizer profiling
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
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.plans/
auto_test/results/experiment_onoff_YYYYMMDD_HHMMSS_tN.profiles/
```

The default all-version run additionally writes `*_v1.csv`, `*_v2.csv`,
`*_v3.csv`, and `*_v3_selectivity_stress.csv`, plus one `*_all.csv` raw table.
Every row explicitly records `experiment_group`, `corpus_version`,
`corpus_scope`, `workload_category`, and `query_class`; the four headline
categories are `v1`, `v2`, `v3_aggregation`, and `v3_selectivity_stress`.
Its `*_statistics/` directory contains `benchmark_statistics.csv`,
`phase_summary.csv`, `optimizer_summary.csv`, `optimizer_phases.csv`,
`optimizer_phase_summary.csv`, `statistics.json`, and `STATISTICS.md`.

`run_all.sh` includes the corpus label, for example
`experiment_onoff_benchmark_YYYYMMDD_HHMMSS_t16.csv` and
`experiment_onoff_benchmark_YYYYMMDD_HHMMSS_t32.csv`.

With `--out path/name.txt`, a sweep writes `path/name_t16.txt` and
`path/name_t32.txt`, with matching CSV names. For a single configuration the
explicit output path is used unchanged. Each CSV contains one row per query
and records `aggregate_query`, `aggregate_pushdown_applied`, `timing_status`,
`timing_threads`, `tm_off`, `tm_on`, and `tm_speedup`. A `fallback-skip` row has
no fabricated runtime pair and records `tm_speedup=1.000` as a policy default. New outputs
contain no `t1_*` columns. Appended `profile_*` columns record status, actual
thread count, R1/R2/R3 operator work and counts, Other CPU work, wall latency,
total CPU work, phase shares, sample count, and the raw profile directory.
The `optimizer_*` columns record paired DuckDB/OuterYan total optimization time,
the measured workflow-phase sum, residual optimizer time, one-sample count, and
workflow-phase JSON maps. When profiling is disabled or skipped, these measurements
remain unavailable.
Each failed profiled query retains its post-warm-up OFF/ON JSON files, compact
decision trace, and CLI log. Successful intermediate profiles are deleted. Timed-out queries are not
retried, and no separate attempts CSV is produced.

Live stderr and the TXT report use one clearly separated block per query:

```text
====================================================================================================
[ 63/185] query=derived__example
  result: correct=TRUE reorder=1 selected=OUTERYAN kernel=bitmap(b=3,h=0) threads=16 runtime_s=[DuckDB=12.000000000 OuterYan=6.000000000] speedup=2.000 optimization_s=[status=OK DuckDB=... OuterYan=...]
  context: family=tpch category=v2 nrel=5 pass=main note=OK ... breakdown_s=[status=OK CPU=... R1=... R2=... R3=... Other=...]
  decision: plan=[mode=GATED reason=COST_OUTERYAN_BETTER ... formula=...] optimizer_phases=[...] cost=[...] SJ=[...]
```

The record always uses four lines: query identity; result/runtime/optimization;
family and phase breakdown; and decision/formula details. Full workflow-phase
maps remain in CSV rather than making the live text block unreadable.
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
| Line 1 | Query index and name |
| Line 2 | Correctness, reorder/selection, kernel, unprofiled runtime/speed-up, and optimizer totals |
| Line 3 | Family/category/path/pass, relation count, note, and phase breakdown |
| Line 4 | Decision mode, formula/cost operands, focused OuterYan pass timings, notices, and optional artifacts |

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
`unary_filter_selectivity`, `low_selectivity_cost_gate_eligible`,
`low_selectivity_cost_gate_selected`, `low_selectivity_cost_ratio_limit`,
`baseline_join_input_rows`, `candidate_join_input_rows`,
`candidate_to_baseline_join_input_ratio`,
`semijoin_retained_cardinality_ratio`,
`uncertain_filter_cardinality_amplification`, `round1_pairs`,
`round1_filters`, `round2_pairs`, and `round2_filters`.
`effective_pass` remains `main` for schema compatibility. The final text summary groups speed-ups separately by
`outer_reordered` and `outer_yan_selected`, and reports query, correct, and timed
counts for every relation depth present in the run.

`plot_speedup.py` writes one multi-page review PDF and, with
`--split-output-dir`, the two publication figures used by the paper:

- `speedup_all_queries.pdf`: panel (a) maps DuckDB runtime to the x-axis and
  DuckOuterYan runtime to the y-axis for every measured query; panel (b) shows the
  per-family distribution of `DuckDB / DuckOuterYan` on a log axis. Family is
  encoded by color and includes fallback-skip defaults at `1.0`. In panel (a), a circle denotes faster/equal and an `X`
  denotes slower. The diagonal and `1x` line denote parity. This figure is not
  sampled.
- `phase_breakdown_outeryan.pdf`: the left panel shows the Round 1, Round 2,
  Round 3, and Other shares of accumulated profile CPU work. The right panel
  directly pairs the unprofiled DuckDB and DuckOuterYan wall times for the same
  query and prints the speed-up at the outer edge. Benchmark blocks are
  separated by horizontal rules.

The retired `runtime_outeryan_queries` and `representative_queries.json` files
are removed on regeneration. The phase figure is emitted only when complete
profiles exist. By default, it samples OuterYan-selected queries, including
regressions. Each family receives up to `--representatives-per-benchmark`
(default 15) slots; shapes are allocated round-robin and OFF-runtime ranks are
sampled evenly within each shape. Sampling never ranks speed-up. The exact
displayed query names, short IDs, order, phase values, and unprofiled baselines
are written to `phase_queries.json`.

Phase components are aggregate operator CPU work across threads. They sum to
`profile_cpu_time_s`, not to `profile_wall_time_s`; parallel CPU work may exceed
elapsed wall time. The plot therefore normalizes the left bars to CPU percent
and keeps the wall-time comparison in a separate right panel. Short IDs use
`G/H/D/J` for graph/TPC-H/TPC-DS/JOB and
`LD/RD/B/S/A/I/O` for left-deep/right-deep/bushy/star/aggregate/industry/other.

Complete descriptive statistics are exported as `STATISTICS.md` and
`statistics.json`, in the split output directory unless `--statistics-dir`
overrides it. Statistics use the full deduplicated run, not the displayed phase
sample, and report all queries, OuterYan-selected queries, and DuckDB-selected
queries separately. Generated groups include benchmark, input shape,
benchmark-by-shape, and manifest-backed structural/evaluation components.
Outputs include exact coverage, measured/fallback counts, min/max queries,
arithmetic/geometric means,
median and percentiles, sample dispersion, faster/slower bands, paired runtime
totals, total-time speed-up, saved time, and complete phase-profile summaries.
The JSON retains calculation precision; Markdown rounds to six decimals.
Speed-up distributions include the explicit fallback default `1.0`; paired
runtime distributions and totals use measured OFF/ON pairs only.

Result files are grouped by filename timestamp before plotting. A final CSV and
its `.attempts.csv` companion form one logical run, not two. Duplicate
`(family, query)` rows use the final CSV value; attempts only fill missing final
queries. `_t16` and `_t32` runs remain separate. An explicit
`--phase-placeholder-csv` is supported for historical results without current
profiles, is visibly labeled, and never contributes to current runtime
statistics.

The September 16 plots and statistics were produced from the retired FULL-heavy
revision and are historical artifacts only. Regenerate figures and tables only
after a complete `v1-mixed-graph25-20260925` run; do not combine its SQL with those old
timings.

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
  -f auto_test/outerjoin_benchmark/benchmark/tpch/derived__ojb_tpch_q03_order_revenue_ldmx.sql

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
# OuterYan for every v1 query in auto_test/outerjoin_benchmark/benchmark. No PG plan is generated
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

The default v1 comparison stage walks all 224 SQL files under
`outerjoin_benchmark/benchmark`: 25 Graph, 54 TPC-H, 63 TPC-DS, and 82 JOB
queries. It executes each bare query
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
OY_CORPUS=auto_test/outerjoin_benchmark/benchmark \
  bash auto_test/experiment_onoff.sh --only all
```

`run_all.sh` and `build_db.sh` reuse existing database files. If a requested
scale or graph differs from the database already on disk, rebuild that database
explicitly with `FORCE=1` before running the experiment.
