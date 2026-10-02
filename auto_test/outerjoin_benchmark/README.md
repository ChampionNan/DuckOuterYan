# Outer-join benchmark: balanced, historically screened candidates

Revision: `balanced-screened-20261002`. The active `benchmark/` contains **720
distinct candidate SQL queries**, **180 per execution family**. These are not
720 verified successful measurements. Final membership requires tests on cpu9.

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

Types: 384 `join`, 162 `graph` (including 27 industry-inspired controls), and
174 `aggregate`. Aggregates comprise 66 COUNT, 36 MIN, 36 MAX and 36 SUM queries.
Type and family differ: `--only graph` runs 180 Graph-family candidates, whereas
`--query-type graph` selects 162 graph/control queries across families.

## Sources and screening

Business-schema derived queries retain relations and **all equality keys per
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

```bash
cd /home/data/bchenba/DuckYanOuter
git pull --ff-only
bash auto_test/run_all.sh --all --timeout 1800
```

`run_all.sh` builds, reuses/builds databases, regenerates and runs the candidates.
`experiment_onoff.sh` alone **does not compile**. Default timeout is 30 minutes
per statement; a timeout ends that query's test without doubling or retrying.
Successful timing keeps one warm-up plus three timed executions per side (median).
Optimization profiling uses one post-warm-up sample. Thus 30 minutes is not a
total budget for all stages of a successful query.

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
30-minute configuration and audited bands. Database changes require re-audit and
remeasurement. The signature is a guard, not a full database checksum.

Final eligibility: correctness verified, both measured runtimes **>1 s and
<1,800 s**, DuckDB/OuterYan **>=0.8**, and verified selectivity band.
Unexecuted `fallback-skip` rows are excluded, never interpreted as measured 1×.
Latest supplied observations win, including failures; no fastest-run selection.
Missing/failed rows yield shortages, never fabricated success or rescaled timings.

Outputs under `qualified_TIMESTAMP/`:

- `qualification.csv`: every candidate and its inclusion/exclusion reason.
- `coverage.csv`: eligible count and shortage per family/tier (target 60).
- `qualification_summary.json`: status and per-family geomean/min/max/median/std.
- `qualified_results.csv`: retained result rows, separate from raw results.
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
  bash auto_test/experiment_onoff.sh --all --timeout 1800
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
