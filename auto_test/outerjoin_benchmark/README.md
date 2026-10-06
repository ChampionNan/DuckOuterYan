# Outer-join benchmark: balanced, historically screened candidates

Base revision: `balanced-screened-20261002`, with the primary-batch
`tpcds-recovery-20261005` component pinned in `tpcds_refresh.json` and the manifest.
The active `benchmark/` contains **729 queries**: **179 Graph**, **179 TPC-H**,
**194 TPC-DS**, and **177 JOB**. The cumulative all-family speed-up screen is
pinned in `sources/speedup_screen_20261007.json` and `benchmark/speedup_screen.json`.
TPC-DS removes 28 timed-out and 8 measured speed-up <0.5 queries from the
20261002 run, retains 147 definitions, and initially adds 54 recovery candidates.
The 20261005_201226_t32 TPC-DS run completed all 201 equivalence checks, with
43 measured pairs, 158 fallback-skip rows and no timeout. Seven measured
speed-ups below 0.5 are now retired: 47 recovery candidates remain, and the
194 active TPC-DS queries contain 36 measured pairs plus 158 fallback-skip rows.
The target of about **50 complete TPC-DS measured pairs is not yet achieved**:
unexecuted fallback policy defaults are not measured pairs. Other families
still contain queries that timed out; this screen does not remove those queries.

| Family | Low `(0,5%)` | Medium `[5,40%)` | High `[40,60%]` | Total |
|---|---:|---:|---:|---:|
| Graph | 59 | 60 | 60 | 179 |
| TPC-H | 59 | 60 | 60 | 179 |
| TPC-DS | 69 | 63 | 62 | 194 |
| JOB | 60 | 59 | 58 | 177 |

Before exact-query screening, Graph/TPC-H/JOB had 60 expressions per shape,
20 of each shape per selectivity band. Graph and TPC-H now each have 59 left-deep,
60 right-deep and 60 bushy expressions; JOB has 60/57/60 respectively.
The active set is no longer exactly balanced. Shapes describe input expressions,
not physical plans or join-graph topology. Every query mixes join kinds; some
use only outer joins, but none uses only FULL joins. I/L/R/F edge totals are
approximately balanced, not claimed exactly equal. TPC-DS shape counts are
reported in `benchmark/design_summary.json`; do not claim exact shape balance
for its performance-conditioned recovery component.

Graph now has **126 four-relation and 53 five-relation queries; no six-relation queries**.
The base generator uses a 14/6 split per selectivity-by-shape cell; the active
low/left-deep cell has 14/5 after removing one measured slow query.
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

Current types: 372 `join`, 162 `graph` (including industry-inspired controls), and
195 `aggregate`. Aggregates comprise 89 COUNT, 34 MIN, 36 MAX and 36 SUM queries.
Type and family differ: `--only graph` runs 179 Graph-family candidates, whereas
`--query-type graph` selects 162 graph/control queries across families.

## All-family speed-up screen

The 20261002_213551_t32 run contains 13 verified measured queries with
DuckDB/OuterYan <0.5. Eight TPC-DS definitions were already retired above;
this screen additionally removed one Graph, one TPC-H and three JOB queries.
The new 20261005_201226_t32 TPC-DS batch contributes seven further exact-query
exclusions (six COUNT queries and one join query), applied on 20261007.
Only the exact measured SQL is excluded, not all tiers of its join expression.
Equality at 0.5 is retained. No additional timeout or fallback is removed.

`benchmark/speedup_excluded.csv` lists all twelve additional exclusions and timings.
The first five SQL definitions and original manifest rows remain recoverable under
`revisions/retired_speedup_20261005/benchmark/`; the new seven are archived under
`revisions/retired_speedup_20261007/benchmark/`. The cumulative policy preserves
both measurement sources. Raw result CSVs are unchanged.
Normal regeneration reapplies the frozen screen without accessing `results/`.
The primary manifest uses speed-up >=0.5 for all families' subsequent qualification;
existing runtime requirements and legacy/reserve policies remain unchanged.

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
