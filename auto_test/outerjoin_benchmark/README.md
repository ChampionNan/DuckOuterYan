# Outer-join benchmark: balanced, historically screened candidates

Revision: `balanced-screened-20261002`. The active `benchmark/` contains **723
distinct candidate SQL queries**: **720 balanced candidates**, 180 per execution
family, plus **three historical TPC-DS case studies**. Thus default runs contain
183 TPC-DS queries and 180 each for Graph, TPC-H and JOB. These are not verified
successful measurements. The following quotas apply only to the balanced 720;
final membership requires tests on cpu9.

| Family | Low `(0,5%)` | Medium `[5,40%)` | High `[40,60%]` | Total |
|---|---:|---:|---:|---:|
| Graph | 60 | 60 | 60 | 180 |
| TPC-H | 60 | 60 | 60 | 180 |
| TPC-DS | 60 | 60 | 60 | 180 |
| JOB | 60 | 60 | 60 | 180 |

Each family also has 60 left-deep, 60 right-deep and 60 bushy input expressions:
20 of each shape in each selectivity band. Shapes describe input expressions,
not physical plans or join-graph topology. Every query mixes join kinds; some
use only outer joins, but none uses only FULL joins. I/L/R/F edge totals are
approximately balanced, not claimed exactly equal.

Balanced types: 384 `join`, 162 `graph` (including 27 industry-inspired controls), and
174 `aggregate`. Aggregates comprise 66 COUNT, 36 MIN, 36 MAX and 36 SUM queries.
Type and family differ: `--only graph` runs 180 Graph-family candidates, whereas
`--query-type graph` selects 162 graph/control queries across families.
The three historical cases add three `join` queries (387 in the full run).

## Historical supplementary cases

Default `--all` also runs the following exact archived SQL definitions. Regeneration
preserves their SQL bytes and verifies pinned hashes; reserve batches do not repeat them.

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

The manifest marks `evaluation_role=historical_slow_baseline_case` and
`semantic_tier=historical_unbanded`. Raw experiment CSVs include all three;
qualification excludes them from the 720-target quotas and writes their raw
observations, **including failures**, to `supplementary_results.csv`. This file
is unqualified case-study evidence, not another screened subset. Selectivity
audits explicitly list these cases as outside the three-band audit.

To test only these cases using an already compiled binary:

```bash
bash auto_test/experiment_onoff.sh --all --timeout 900 \
  --query-list auto_test/outerjoin_benchmark/benchmark/historical_cases.txt
```

A uniform 15-minute run is now the default (`run_all.sh --all`),
but Q80-alt historically needed about 19 minutes on the DuckDB side. SF50 may be
faster; it is not guaranteed to fit within 900 seconds. The default and balanced
qualification policy are both 900 seconds. Old 1800-second results retain their
recorded limits and are not qualified under the new 900-second policy.
OFF correctness runs first: an OFF timeout
stops that query before ON, so it does not establish that OuterYan itself timed out.

## Sources and screening

Balanced business-schema derived queries retain relations and **all equality keys per
edge** from pinned TPC-H, TPC-DS, JOB and SQLStorm seeds. Synthetic graph shapes
are independently enumerated chains, stars and branches (4–6 relations, forward
and converging edges). Industry controls are separately identified as synthetic,
not claimed to originate in a source workload.

`sources/balanced_design.json` pins predicates, adaptations and local calibration.
Filters replace WHERE, without modulo/hash sampling. Graph filters use vertex
cohorts; business filters use dates, years, categories, names and ranges.
Selectivity includes NULL base rows in its denominator, not final join output
or cost-model estimates. Local calibration requires a target-database audit.

`sources/balanced_exclusions.json` pins historical speed-up <0.8 or confirmed
1,800-second timeout observations. Their unchanged join expressions are excluded
across tiers. 600-second timeouts are not assumed to be 1,800-second failures.
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
running the main workflow. Graph/JOB, SQL definitions and cost model are unchanged;
the default timeout is now 900 seconds. Re-audit selectivity/plan choices on the new
databases; do not pool measurements across SF100 and SF50.

```bash
cd /home/data/bchenba/DuckYanOuter
git pull --ff-only
export TPCH_SF=50 TPCDS_SF=50
bash auto_test/run_all.sh --all --timeout 900
```

`run_all.sh` builds, reuses/builds databases, regenerates and runs the candidates.
`experiment_onoff.sh` alone **does not compile**. Default timeout is 15 minutes
per statement; a timeout ends that query's test without doubling or retrying.
Successful timing keeps one warm-up plus three timed executions per side (median).
Optimization profiling uses one post-warm-up sample. Thus 15 minutes is not a
total budget for all stages of a successful query.
An existing `OY_TIMEOUT_SECS` environment variable or explicit `--timeout` still
overrides the default; unset stale overrides when using the default workflow.

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
15-minute configuration and audited bands. Database changes require re-audit and
remeasurement. The signature is a guard, not a full database checksum.

Final eligibility: correctness verified, both measured runtimes **>1 s and
<900 s**, DuckDB/OuterYan **>=0.8**, and verified selectivity band.
Unexecuted `fallback-skip` rows are excluded, never interpreted as measured 1×.
Latest supplied observations win, including failures; no fastest-run selection.
Missing/failed rows yield shortages, never fabricated success or rescaled timings.

Outputs under `qualified_TIMESTAMP/`:

- `qualification.csv`: every candidate and its inclusion/exclusion reason.
- `coverage.csv`: eligible count and shortage per family/tier (target 60).
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
  bash auto_test/experiment_onoff.sh --all --timeout 900
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
