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
| `representative_queries.txt` | Ordered P0/P1 cross-family validation manifest, including runnable 3–7 relation cases |
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
| `OY_TIMEOUT_SECS` | `900` | Per-statement timeout; `0` disables it |
| `OY_BATCH_GRACE_SECS` | `30` | External timing-batch startup/serialization grace |
| `OY_RUNS` | `3` | Positive odd number of timed executions after one warm-up |
| `OY_CAPTURE_PLANS` | `0` | Save OFF/ON EXPLAIN, optimizer trace, and cost-step artifacts |
| `OY_CORPUS` | `auto_test/outerjoin_query` | Corpus root |
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
4. Run one profiled warm-up followed by `--runs N` profiled OuterYan-ON
   executions at `threads=1` using `.mode trash`. Keep the complete tuple
   associated with the median high-resolution JSON query latency. Sum native
   `OPERATOR_TIMING` values for round-1 semi-join operators, round-2 semi-join
   operators, and real-join operators. The traced plan supplies planned pair
   and newly built filter counts for each round.
5. Time OuterYan OFF and ON at `threads=1` and `threads=$OY_THREADS`. Each batch
   has one warm-up followed by `--runs N` timed executions; the median excludes
   the warm-up.
The profile denominator is labeled `Total-Time`: the median JSON query latency
from that profiled single-thread batch. Each numerator and `Total-Time`
therefore come from a matched execution. `Other = Total-Time - R1 - R2 - R3`,
so the four components close the same sample. They are active operator times,
not contiguous phase wall times. R1 matches `SJ_BUILD_ROUND_1` and
`SJ_PROBE_ROUND_1`; R2 matches the round-2 names. R3 matches DuckDB's physical
join types (`HASH_JOIN`, nested-loop, merge, IE, delim, positional, ASOF, and
cross-product variants). `Other` includes unmatched operators and work outside
native operator timing, such as planning, scheduling, state setup, waits, and
profiler overhead. Times are converted to integer nanoseconds before
subtraction. The log renders ratios as percentages; the CSV retains ratios in
`[0,1]`.
Profiling serialization and CLI output are outside Total-Time. Total-Time is
labeled separately because profiling instrumentation can change its measured
time. T1/TM run in fresh `-no-init` CLI processes and explicitly disable
profiling before `.timer on`; no custom production phase instrumentation is
used.

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
baseline_threshold = MAX_CANDIDATE_TO_BASELINE_RATIO * baseline_cost

select OuterYan iff candidate_total <= baseline_threshold
```

Cost formula V3 applies two consistency checks before that final comparison.
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

The trace and CSV report two separate comparisons: `raw_cost_winner` compares
`candidate_total` directly with `baseline_cost`, while `gate_result` compares
`candidate_total` with `baseline_threshold`. `selected_plan` is the plan that
is actually returned and can differ because of same-grouping or proven-empty
policy decisions.

The policy knobs are `constexpr` members of `OuterYanOptimizer` in
`src/include/duckdb/optimizer/outer_yan/pipeline/outer_yan_optimizer.hpp`; they
are not environment variables or SQL settings. The current workspace selects
`GATED`, uses a semi-join ratio of `0.35`, and keeps a baseline limit
of `1.0`. Under GATED, this selects OuterYan only when its estimated total cost
does not exceed the DuckDB baseline. Rebuild the CLI after changing these
source-level settings.

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
| `COST_DUCKDB_BETTER` | Changed candidate exceeded the configured threshold |
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
GRAPH_DATASET=bitcoin OY_THREADS=1 \
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
`path/name.csv`. Each CSV contains exactly one row per query. The historical
attempts CSV is retained for downstream compatibility and is an identical
single-attempt copy; timed-out queries are not retried.

Live stderr and the TXT report use one clearly separated block per query:

```text
====================================================================================================
[ 63/265] oy_th_th_bushy4b_v1  correct=TRUE reorder=1 selected=OUTERYAN kernel=bitmap(b=3,h=0) profile=[Total-Time=45.696000000s R1=NA(no-pairs,pairs=0) R2=0.940435000s(2.06%,pairs=3,filters=3,operators=N) R3=12.297079000s(26.91%,operators=N) Other=32.458486000s(71.03%)] TM:... T1:...
  details: family=tpch sql=... pass=main timeout=900s note=OK ... decision=[mode=FORCE_OUTERYAN reason=FORCE_OUTERYAN ...] cost=[...] SJ=[R1(... pairs=0 filters=0) R2(... pairs=3 filters=3) ...]
```

The record always uses two lines: line 1 contains the high-level result,
kernel choice, phase profile, and timing; line 2 contains decision/cost metadata.
Applicable queries include the OuterYan and
DuckDB cost formula, gate comparison, and join/SJ weights on line 2. With plan
capture enabled, that line also lists the DuckDB-OFF and enabled EXPLAIN files,
full trace, and per-join/per-SJ cost records.

`pairs` counts planned semi-join applications in that round. `filters` counts
new filter constructions; a reused filter contributes another pair without
another filter. `R1=NA(no-pairs,pairs=0)` therefore means that round was not
scheduled, rather than that its timer incorrectly measured zero. If DuckDB was
selected, both rounds show `NA(no-sj-plan)`. A missing plan count or profile is
reported explicitly instead of being displayed as a valid zero. In particular,
`profile-missing` means the plan expected at least one pair but the runtime
profile observed no matching physical operator for that round.

Each query block includes:

| Field | Meaning |
|---|---|
| Line 1 | Query/result, selected plan, kernel counts, profiled Total-Time decomposition, and OFF/ON speed-up for TM and T1 |
| Line 2 | Family/path/pass, decision mode, cost/gate operands, SJ work, weights, hash notices, and optional artifacts |

Each applicable, costed query includes raw cost components and an expanded
gate:

```text
gate formula: candidate_join + semijoin_ratio * semijoin_raw <= baseline_ratio * baseline
gate values:  <join> + <sj-ratio> * <raw-sj> <= <baseline-ratio> * <baseline>
gate result:  <candidate-total> <= <threshold> => PASS|FAIL -> <decision>
```

For same-grouping, inapplicable, unavailable, or forced-policy cases, the report
states that the numeric gate was skipped and prints the decision reason.

The CSV exports the same decision, cost, kernel, correctness, timing, and phase
fields in machine-readable form, including the SQL-derived `relation_count`,
`default_filter_upper_bound_checked`, `default_filter_upper_bound_selected`,
`uncertain_filter_amplification_guard`,
`semijoin_retained_cardinality_ratio`,
`uncertain_filter_cardinality_amplification`, `round1_pairs`,
`round1_filters`, `round2_pairs`, `round2_filters`, and the native operator
counts.
`effective_pass` remains `main` for schema compatibility. The final text summary groups speed-ups separately by
`outer_reordered` and `outer_yan_selected`, and reports query, correct, and timed
counts for every relation depth present in the run.

`plot_speedup.py` renders separate per-family phase figures named
`phase_breakdown_<family>`. Each query has grouped R1, R2, R3, and residual
`Other` elapsed-time bars on a base-10 logarithmic x-axis, plus a marker and
label for its matched profiled total. This keeps small R1/R2 measurements
visible beside much larger phases. Structurally absent DuckDB R1/R2 phases are
blank; incomplete or internally inconsistent profiles are omitted rather than
converted to zero.

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
