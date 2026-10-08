# Outer-join benchmark: balanced, historically screened candidates

Base revision: `balanced-screened-20261002`, with the primary-batch
`tpcds-recovery-20261005` component pinned in `tpcds_refresh.json` and the manifest.
The active `benchmark/` contains **724 queries**: **176 Graph**, **176 TPC-H**,
**206 TPC-DS**, and **166 JOB**. The cumulative exact-SQL speed-up screen is
pinned in `sources/speedup_screen_20261008.json` and `sources/retirements_20261008.json`.
TPC-DS removes 28 timed-out and 8 measured speed-up <0.5 queries from the
20261002 run, retains 147 definitions, and initially adds 54 recovery candidates.
The 20261005_201226_t32 TPC-DS run completed all 201 equivalence checks, with
43 measured pairs, 158 fallback-skip rows and no timeout. Seven measured
speed-ups below 0.5 are now retired: 47 recovery candidates remain, and the
194 previously measured TPC-DS definitions contain 36 measured pairs plus 158 fallback-skip rows.
The 20261008 extension adds 15 new three-tier candidates, now measured at SF50;
historical timings are not measurements of these new SQL definitions.
The target of about **50 complete TPC-DS measured pairs is not yet achieved**:
unexecuted fallback policy defaults are not measured pairs. Other families
still contain queries that timed out; this screen does not remove those queries.

| Family | Low `(0,5%)` | Medium `[5,40%)` | High `[40,60%]` | Total |
|---|---:|---:|---:|---:|
| Graph | 56 | 60 | 60 | 176 |
| TPC-H | 58 | 59 | 59 | 176 |
| TPC-DS | 73 | 67 | 66 | 206 |
| JOB | 52 | 58 | 56 | 166 |

Before exact-query screening, Graph/TPC-H/JOB had 60 expressions per shape,
20 of each shape per selectivity band. Graph now has 58/59/59 expressions;
TPC-H has 59 left-deep, 60 right-deep and 57 bushy expressions, and JOB has
59/53/54 respectively.
The active set is no longer exactly balanced. Shapes describe input expressions,
not physical plans or join-graph topology. Every query mixes join kinds; some
use only outer joins, but none uses only FULL joins. I/L/R/F edge totals are
approximately balanced, not claimed exactly equal. TPC-DS shape counts are
reported in `benchmark/design_summary.json`; do not claim exact shape balance
for its performance-conditioned recovery component.

Graph now has **124 four-relation and 52 five-relation queries; no six-relation queries**.
The base generator uses a 14/6 split per selectivity-by-shape cell; the active
low/left-deep and low/right-deep cells have 13/5 and 14/5, and low/bushy has 13/6,
after exact-query retirement.
The graph database and dataset are unchanged. Reserve batches retain the base quota.

Graph names include `__inputcap1__` to distinguish the new filtered inputs from
old measurements. R1 retains `src <= 2/83/306` (local Bitcoin fractions
2.83%/30.00%/54.99%). Every other participating relation uses a pre-join source
cap `src <= 10/20/40`, with local marginal fractions 9.33%/14.35%/21.19%.
These predicates are inside each relation's scan subquery, not added to the
root WHERE: filtering NULL-padded output there could erase preserved rows.
The three balanced tiers refer to **R1's primary cohort**, not every input.
Do not multiply these correlated marginal fractions to estimate join selectivity.
`input_filter_profiles_json` in the manifest records each input/predicate;
the harness saves a per-run manifest snapshot. Server audits count R2..Rn
independently and qualification requires every input cap to pass its own band.
The caps were not selected using ON/OFF speed-ups. They reduce the input scale
but cannot guarantee a sub-600s run, a >1s runtime, or eligibility of every candidate.

Current types: 375 `join`, 164 `graph` (including industry-inspired controls), and
185 `aggregate`. Aggregates comprise 118 COUNT (85 global, 33 grouped),
19 MIN, 24 MAX and 24 SUM queries.
Type and family differ: `--only graph` runs 176 Graph-family candidates, whereas
`--query-type graph` selects 164 graph/control queries across families.

## COUNT(*) replacements (20261008)

The `aggregate-count-20261008` component replaces 39 previously selected
MIN/MAX/SUM queries without realized aggregate pushdown: 6 Graph, 18 TPC-H,
and 15 JOB. Only the aggregate expression changes to `COUNT(*)`; the original
GROUP BY, FROM expression, join types, predicates and three selectivity tiers
are preserved. This is a workload change to use the supported count path,
not an optimizer improvement or a guarantee of selection, speed-up or completion.

New names end in `__grouped_count`. Their SQL hashes and fingerprints differ
from the old queries, whose definitions and metadata remain recoverable under
`revisions/retired_aggregate_count_20261008/benchmark/`. Do not reuse the old
SUM/MIN/MAX timings for these replacements. Total and per-family counts stay
unchanged; other aggregate definitions, including existing COUNT(*), are unchanged.
The generator applies the frozen `sources/aggregate_count_refresh_20261008.json`
policy without inspecting results. Its focused new-query list is
`benchmark/aggregate_count_refresh.txt` (33 active queries).

All 39 replacements passed local bare-query OFF/ON result-multiset comparison
(78 executions, no errors or timeouts), using the existing Release binary,
TPC-H SF1, the local JOB database, and Bitcoin Graph data. The six Graph plans
also contain actual pushed aggregates below joins. The bounded checks and
binary provenance are recorded in
`sources/aggregate_count_refresh_20261008_local_smoke.json`; they do not replace
CPU9 SF50 measurements or establish a performance improvement.

After local correctness checks, the SF50 performance retest uses the existing
Release binary, 32 threads, one unprofiled post-warmup sample, separate profiles,
independent 600-second OFF/ON timeouts, and no full server-side result comparison:

```bash
TPCH_SF=50 TPCDS_SF=50 SKIP_BUILD=1 SKIP_DATA=1 SKIP_QUERY_GEN=1 \
  bash auto_test/run_all.sh --only all --query-type aggregate --threads 32 \
  --runs 1 --duckdb-timeout 600 --outeryan-timeout 600 \
  --no-check-correctness --profile --capture-plans \
  --query-list auto_test/outerjoin_benchmark/benchmark/aggregate_count_refresh.txt
```

## TPC-DS three-tier extension (20261008)

The initial `sources/tpcds_extension_20261008.json` selected five historical
mixed-join expressions. The SQLStorm 11376 bushy low/medium/high variants then
timed out on both sides at SF50. Their item-only `store_sales`/`web_sales` join
multiplies fact rows; replacing the old stacked sampling with a 3% customer
cohort did not bound joined output. Both 11376 structures (six queries) are
therefore retired: the three bushy timeouts are observed, while the left-deep
triple is removed for the same structural risk, not labeled as measured timeouts.
Old SQL and evidence are preserved in revisions and the frozen policy.

The r2 extension retains the other nine definitions unchanged and introduces
six SQLStorm 14368 connected-subgraph variants. Each has one `web_sales` fact
and dimensions connected through the original equality keys. The new four-table
right-deep variant omits date and ship mode; the five-table bushy variant omits
ship mode. Join types remain mixed. These are new source-derived expressions,
not exact historical queries, so no historical speed-up is attributed to them.

| Active expression | Shape | Relations | Historical source speed-up |
|---|---|---:|---:|
| SQLStorm 14368 chain4 (r2) | right-deep | 4 | not measured for this expression |
| SQLStorm 14368 branch5 (r2) | bushy | 5 | not measured for this expression |
| SQLStorm 14368 alternate bushy | bushy | 6 | 1.0405 |
| SQLStorm 28643 alternate bushy | bushy | 6 | 0.9040 |
| line4a control | left-deep | 4 | 4.7102 |

The nine retained queries keep their archived FROM expressions; the six r2
queries use the documented subgraphs. All use `SELECT *` and current
low/medium/high cohorts. The 15 are non-aggregate: 9 bushy, 3 left-deep and
3 right-deep, with five per tier.
This adds bushy coverage absent from the previous 36 measured TPC-DS pairs; it
does not claim exact shape balance. SQLStorm uses customer identifier buckets
at 3/30/55%; the control uses demographics-key prefixes with the same calibrated
fractions. These are base-entity cohorts, not joined-output selectivity or
business-semantic categories. The CPU9 audit rechecks the profiles on SF50.

This remains performance-conditioned curation, now also conditioned on timeout
feasibility; it is not an unbiased sample or an optimizer improvement. Q97 is
still omitted because its historical running time was already large.
The historical runs used SF50, 32 threads and three-run medians. The new SQL and
one-sample protocol differ: old times are provenance only, never merged into
current statistics. The target is about 50 measured selected pairs, not a promise
that all 15 will select OuterYan or avoid timeouts. Before retesting, there are
still only 36 valid measured TPC-DS pairs. Do not force plan selection or insert
fallback defaults to reach 50; retain every new outcome for review.
The SF50 bounded feasibility checks are recorded separately in
`sources/tpcds_extension_20261008_r2_pilot.json`. All six replacements completed
on both sides within the 60-second pilot cap, but the bushy triple selected
DuckDB. These uncontrolled-cache pilot times are not paper measurements.
The retest retains raw outcomes without speed-up filtering; the separate,
optional qualifier still uses the existing manifest thresholds.

Normal `--all` and `--only tpcds` runs include the extension. To build and retest
only these 15, reusing existing databases without deleting them:

```bash
env SKIP_DATA=1 TPCDS_SF=50 OY_RUNS=1 OY_PROFILE=1 OY_CHECK_CORRECTNESS=0 \
  bash auto_test/run_all.sh --all --threads 32 --timeout 600 \
  --query-list auto_test/outerjoin_benchmark/benchmark/tpcds_extension.txt
```

Both sides have separate 600-second statement limits. The profile and ordinary
warmup are excluded from the single reported timing. This performance-only
command does not perform result-equivalence checks. All original 718 SQL
definitions, archived exclusions and raw result files remain unchanged.

## All-family speed-up screen

The 20261002_213551_t32 run contains 13 verified measured queries with
DuckDB/OuterYan <0.5. Eight TPC-DS definitions were already retired above;
this screen additionally removed one Graph, one TPC-H and three JOB queries.
The new 20261005_201226_t32 TPC-DS batch contributes seven further exact-query
exclusions (six COUNT queries and one join query), applied on 20261007.
Only the exact measured SQL is excluded, not all tiers of its join expression.
Equality at 0.5 is retained. No additional timeout or fallback is removed.

On 20261008, eleven further exact queries (2 Graph and 9 JOB) were retired after
the full 20261007_161108_t32 run measured DuckDB/OuterYan **<=0.7**. This run used
`correct=NOT-CHECKED` and `correctness_check=disabled`; its observations establish
timings, not result equivalence. All eleven have both runtimes below one second.
Only Graph and JOB are in this new rule's scope; TPC-H and TPC-DS are unchanged.
The inclusive threshold is applied to the unrounded runtime ratio, not the CSV's
rounded display value. The exact SQL identities are frozen: future results do
not dynamically trigger further removals.

`benchmark/speedup_excluded.csv` lists all 23 cumulative exclusions and timings.
The first five SQL definitions and original manifest rows remain recoverable under
`revisions/retired_speedup_20261005/benchmark/`; the next seven are archived under
`revisions/retired_speedup_20261007/benchmark/`. The cumulative policy preserves
all three measurement sources. The eleven new retirements are recoverable under
`revisions/retired_speedup_20261008/benchmark/`. Raw result CSVs are unchanged.
Normal regeneration reapplies the frozen screen without accessing `results/`.
The primary manifest uses speed-up >=0.5 for all families' subsequent qualification;
this unchanged qualification setting is distinct from the frozen Graph/JOB <=0.7
retirement. Existing runtime requirements and legacy/reserve policies remain unchanged.

## TPC-DS historical recovery and removed cases

The three previously restored cases below timed out in the 20261002 correctness
stage and are **no longer active**. They are preserved, together with all 36 removed
definitions, under `revisions/retired_tpcds_20261005/benchmark/`. Raw experiment
results remain unchanged. `benchmark/historical_cases.txt` is now empty.

| Case | Active query ID | Historical DuckDB / OuterYan time (s) |
|---|---|---:|
| Q80-alt | `join__tpcds__historical__q80_alt` | 1137.5 / 9.3 |
| Q80-left-deep | `join__tpcds__historical__q80_left_deep` | 712.5 / 9.2 |
| Q93-left-deep | `join__tpcds__historical__q93_left_deep` | 665.1 / 4.6 |

These timings are from the **20260926 SF100 run**, not predictions or measurements
for SF50. The cases were requested based on historical performance; they are
**not** additional balanced samples. They retain `ss_ticket_number % 1000 = 0`
and the historical item-only sales/returns equality, not a complete transaction
composite key. The modulo filter is nominally about 0.1%, but is not a measured
or audited semantic band. Do not describe these definitions as unchanged original
TPC-DS queries, or as complying with the balanced component's source-key/filter rules.

The replacement component is explicitly marked
`evaluation_role=historical_selectivity_recovery`: initially 18 historical expressions ×
three tiers = 54 candidates (30 global COUNT, 21 join and 3 synthetic-control
queries). After the new exact-query screen, 47 remain: 24 global COUNT, 20 join
and 3 synthetic-control queries. Sources cover Q5, Q40, Q80, Q93,
SQLStorm 10809/14368/28643 and one
industry control. SQLStorm 11376 is not replenished. Archived mixed join types,
parentheses, relations and join keys are retained. Some historical fact/fact
patterns intentionally retain item-only edges and must not be described as
unchanged original TPC-DS queries with complete transaction keys.

For historical modulo patterns, filters remain on the same relation and use
`(identifier % 100) < 3/30/55`, not an unrelated date predicate. These are
deterministic identifier cohorts, **not business-semantic filters**, random
samples, or joined-output selectivity estimates. Q93 reason categories and the
control quantity predicate retain semantic cohorts. Four locally counted
recovery profiles are pinned in `sources/tpcds_refresh_20261005.json`; cpu9
must re-audit their actual fractions. All profiles fit `(0,5%)`, `[5,40%)`,
`[40,60%]` locally. Large-output Q5/Q40/Q80 expressions use explicit COUNT
variants, not a hidden wrapper around timed SQL. Both engines execute the same
bare query. Historical times are selection evidence, never assigned to new SQL.

Exclusions match exact SQL, not every tier sharing an expression. Recovery
expressions initially receive three tiers, but the measured exact-query screen
now leaves some expressions with fewer than three. Changing a query's name cannot restore an
exact query known to time out or run below 0.5× in the pinned comparison runs.
The policy is applied automatically during normal regeneration, without reading
machine-local results. `--batch >0` and custom-size reserve corpora retain the
base design; they do not repeat this primary-batch recovery component.

Build, regenerate and retest all active TPC-DS queries on cpu9:

```bash
bash auto_test/run_all.sh --only tpcds --timeout 600 --check-correctness
```

To retest only the 47 retained recovery candidates with an already compiled binary:

```bash
bash auto_test/experiment_onoff.sh --all --timeout 600 \
  --query-list auto_test/outerjoin_benchmark/benchmark/tpcds_recovery.txt
```

A 10-minute limit for each engine is now the default (`run_all.sh --all`),
but Q80-alt historically needed about 19 minutes on the DuckDB side. SF50 may be
faster; it is not guaranteed to fit within 600 seconds. The default and balanced
qualification policy are both 600 seconds **per engine, independently**. Old
900/1800-second results retain their recorded limits and are not qualified under
the new 600-second policy.
Correctness comparison is enabled by default for every query, including fallbacks.
An OFF timeout does not stop ON or establish an OuterYan timeout (and vice versa).

## Sources and screening

The base business-schema component retains relations and **all equality keys per
edge** from pinned TPC-H, TPC-DS, JOB and SQLStorm seeds. Synthetic graph shapes
are independently enumerated chains, stars and branches (4–5 relations, forward
and converging edges). Industry controls are separately identified as synthetic,
not claimed to originate in a source workload.

`sources/balanced_design.json` pins predicates, adaptations and local calibration.
Base-component filters replace WHERE, without modulo/hash sampling. Recovery
identifier cohorts are the explicitly marked exception above. Graph filters use vertex
cohorts; business filters use dates, years, categories, names and ranges.
Selectivity includes NULL base rows in its denominator, not final join output
or cost-model estimates. Local calibration requires a target-database audit.

`sources/balanced_exclusions.json` pins historical speed-up <0.8 or confirmed
1,800-second timeout observations. Their unchanged join expressions are excluded
across tiers in the base generator. The recovery component explicitly reconsiders
historical expressions with new predicate cohorts and/or projections; it does
not silently rename known failed exact SQL. 600-second timeouts are not assumed to be 1,800-second failures.
TPC-DS Q72's reduced pattern is excluded because its omitted sales/inventory week
constraint produced unsafe fanout. Corrected composite-key expressions are new
candidates, not recipients of old timing measurements.

This is **historically/performance-screened curation**, not an unbiased overall
sample or proof of an advantage over every source query. Full original results
and exclusions remain available. Generation reads frozen sources/evidence, never
machine-local `results/`. Optimizer parameters and estimates are unchanged.

## Local edit → origin → cpu9

Make and validate changes locally, then commit and push the reviewed task changes
to origin. On cpu9, pull them into `/home/data/bchenba/DuckYanOuter` and run:

Both TPC-H and TPC-DS now default to **SF50**. Existing database files are reused,
not resized or scale-verified. On the first migration, stop all tests using the
databases and back up `tpch_db`, `tpcds_db` and any WAL files. Then explicitly run
`FORCE=1 TPCH_SF=50 TPCDS_SF=50 bash auto_test/build_db.sh tpch tpcds` after pulling.
This replaces only the two TPC databases. Skip rebuilding if both existing files
are already known to be SF50. Remove stale scale environment overrides before
running the main workflow. Changing the TPC scale does not change Graph/JOB data
or the cost model. The default timeout is now 600 seconds per engine. Re-audit selectivity/plan choices on the new
databases; do not pool measurements across SF100 and SF50.

```bash
cd /home/data/bchenba/DuckYanOuter
git pull --ff-only
export TPCH_SF=50 TPCDS_SF=50
bash auto_test/run_all.sh --all --timeout 600
```

`run_all.sh` builds, reuses/builds databases, regenerates and runs the candidates.
`experiment_onoff.sh` alone **does not compile**. Default timeout is 10 minutes
per statement per engine; a timeout stops only that engine, without doubling or
retrying. The other engine still executes. `--timeout` sets both limits;
`--duckdb-timeout` and `--outeryan-timeout` override them independently.
Each side uses a fresh process with one ordinary warm-up, one detailed profile,
then one unprofiled timed execution in that same process. Preparatory executions
do not contribute to runtime; optimizer and execution phases share the profile.
Before these stages, every query runs one bare OFF/ON equivalence pair by default.
A mismatch/error stops the query before profiling/timing. A timeout leaves
equivalence unverified but preserves the completed engine's measurements;
speed-up is `NA`, and censored pairs are excluded from paired statistics. Verified
fallbacks skip performance measurements, not equivalence. There is also one
separate ON kernel diagnostic for selected plans, so a completed selected query
uses nine executions, but only the final OFF/ON pair supplies running times.
`--check-correctness` explicitly enforces the default even if an old environment
disables it. With diagnostic `--no-check-correctness`, measured rows remain
`NOT-CHECKED` and `correctness_check=disabled`, not verified correctness.
`--no-profile` retains one ordinary
warm-up before timing. Explicit `--runs N` can request multiple timed samples;
the default is one. Rebuild via `run_all.sh` for profile-only trace emission.
Thus 10 minutes is not a total budget for all stages of a successful query.
`OY_TIMEOUT_SECS` supplies a shared default; `OY_DUCKDB_TIMEOUT_SECS` and
`OY_OUTERYAN_TIMEOUT_SECS` independently override it. CLI per-engine limits take
precedence over the common `--timeout`; unset stale overrides for default runs.

After the run, audit the actual cpu9 databases and qualify the exact result CSV:

```bash
python3 auto_test/gen_outerjoin_benchmark.py --audit-selectivity \
  --audit-timeout 600 --audit-output auto_test/results/cpu9_selectivity_audit.json
python3 auto_test/qualify_benchmark.py \
  --selectivity-audit auto_test/results/cpu9_selectivity_audit.json \
  --results auto_test/results/experiment_onoff_benchmark_TIMESTAMP_t32.csv \
  --output-dir auto_test/results/qualified_TIMESTAMP
```

Replace `TIMESTAMP` with the actual run timestamp. The audit's 600-second limit
is for read-only base counts, not workload timing. Database overrides are
`GRAPH_DB`, `TPCH_DB`, `TPCDS_DB`, `JOB_DB`; run and audit must use the same files.
Qualification checks SQL/manifest hashes, host, database path/size/mtime signature,
10-minute-per-engine configuration and audited bands. Database changes require re-audit and
remeasurement. The signature is a guard, not a full database checksum.

Qualification uses each manifest row's thresholds: the screened primary batch
requires DuckDB/OuterYan **>=0.5 for every family**. TPC-DS keeps positive subsecond
times; the other families retain **both >1s**. Legacy/reserve manifests keep their
own thresholds. Both sides must complete below 600s and pass
the selectivity audit. Correctness is verified unless explicitly disabled.
Unchecked rows remain performance-only evidence, not a correctness claim.
Qualification rejects mixed timing protocols/sample counts/correctness modes;
do not combine old three-run medians and new single-run timings as one experiment.
Unexecuted `fallback-skip` rows are excluded, never interpreted as measured 1×.
Latest supplied observations win, including failures; no fastest-run selection.
Missing/failed rows yield shortages, never fabricated success or rescaled timings.

Outputs under `qualified_TIMESTAMP/`:

- `qualification.csv`: every candidate and its inclusion/exclusion reason.
- `coverage.csv`: eligible count and shortage per family/tier (legacy balanced target 60,
  not the new exploratory goal of about 50 complete TPC-DS pairs overall).
- `qualification_summary.json`: status and per-family geomean/min/max/median/std.
- `qualified_results.csv`: retained balanced result rows, separate from raw results.
- `supplementary_results.csv`: all supplied historical-case observations, unqualified.
- `qualified_manifest.csv`, `qualified_query_paths*.txt`: retained definitions/lists.

`gen_experiment_result.py --date YYYYMMDD` still reports the **full run**.
To plot the screened subset, explicitly supply `qualified_results.csv` and an
output directory; label the population as screened. Do not silently replace
full-run numbers with curated numbers.

## Replenishment and reproducibility

If a family/tier has fewer than 60 eligible queries, add a disjoint reserve batch,
measure it on cpu9, and qualify both batches. SQL is not automatically tuned
using its achieved speed-up.

```bash
python3 auto_test/gen_outerjoin_benchmark.py --batch 1 \
  --root auto_test/outerjoin_benchmark/reserve_1
OY_CORPUS=auto_test/outerjoin_benchmark/reserve_1/benchmark \
  bash auto_test/experiment_onoff.sh --all --timeout 600
python3 auto_test/gen_outerjoin_benchmark.py --audit-selectivity \
  --root auto_test/outerjoin_benchmark/reserve_1 \
  --audit-timeout 600 --audit-output auto_test/results/cpu9_reserve_1_audit.json
```

Pass repeated `--corpus` and `--selectivity-audit` in matching order to the qualifier,
with all matching CSVs after `--results`, oldest first. Selection balances shapes
where possible, then stable query IDs, never achieved speed. Use a new root for
each batch; replacing another batch is rejected.

Former 650-query definitions are retained verbatim in
`revisions/unique_semantic_20260929/benchmark/`, including historical name aliases.
Older definitions remain under other `revisions/` directories. Default runs do not
scan archives. Regeneration rejects edited managed SQL or unmanaged SQL rather
than overwriting them. `--version` remains retired; `--all` is the default corpus.
