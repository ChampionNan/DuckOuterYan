# OuterJoin benchmark: one deduplicated corpus

The active workload is `benchmark/`. It contains **650 distinct SQL queries**:

| Query type | Count | Purpose |
|---|---:|---|
| `join` | 480 | Source-derived join structures at three semantic filter bands |
| `graph` | 68 | Synthetic graph structures over Graph and business schemas |
| `aggregate` | 102 | Root COUNT, SUM, MIN and MAX over source-derived join structures |
| Total | **650** | Each SQL identity is executed once |

Execution-family counts are Graph **31**, TPC-H **175**, TPC-DS **209**, and JOB **235**.
Query type and execution family are separate: `--query-type graph` selects all
68 graph-structure queries, while `--only graph` selects the 31 queries on the
Graph dataset. The former `control__` prefix remains readable in historical results.
The low/medium/high bands contain **218/218/214** queries, respectively.
These are corpus counts before runtime, correctness, timeout and plan-selection exclusions.

## Deduplication and names

The generator combines all former structure, selectivity and aggregation expansions.
Identity is the execution family plus SQL tokens, ignoring comments, whitespace and
unquoted identifier/keyword case. String and quoted-identifier contents, predicates,
join kinds, operand order and parentheses remain significant. This is syntactic
identity, not a claim to recognize every algebraically equivalent query.

The previous 908 workload instances collapse to 650 identities. Two additional
JOB diagnostic aliases also refer to existing identities. All **910** old names
map to canonical names in [`benchmark/aliases.csv`](benchmark/aliases.csv).
Different source queries that yield the same adapted SQL retain every provenance
alias but contribute one observation to the overall benchmark.

Names use `type__family__source_and_structure__join_vector__filter_band`, for example:

```text
join__tpch__q05_region_sales_ldmx__ilrf__sel_low
aggregate__tpch__q05_region_sales_ldmx__ilrf__global_count__sel_low
graph__graph__bushybal_n4_mixa_case03__fil__sel_medium
```

The precise graph-query name follows its retained source metadata; rare name collisions
receive a SQL-hash suffix. No active filename contains a suite version. Join-vector
letters mean INNER/LEFT/RIGHT/FULL. Source slots `ldmx`, `rdmx`, `bmx`, `bdmx`,
`alt`, `rdax` and `rdu*` identify left-deep, right-deep, bushy and alternate forms;
`tree_shape` and `topology` in the manifest give explicit classifications.

The 18 selectivity-sensitivity queries and two JOB regression guards are metadata
subsets, not extra SQL copies. `selectivity_stress.txt` and `job_regressions.txt`
reference paths in the same `benchmark/` directory. The default run does not
execute those queries again.

## Generate and run

```bash
python3 auto_test/gen_outerjoin_benchmark.py
bash auto_test/run_all.sh

# Select by query type or execution family.
bash auto_test/experiment_onoff.sh --query-type join --only tpch
bash auto_test/experiment_onoff.sh --query-type aggregate
bash auto_test/experiment_onoff.sh --query-type graph --only graph --limit 4

# Optional diagnostic reruns of existing identities.
bash auto_test/experiment_onoff.sh --corpus-scope selectivity-stress
bash auto_test/experiment_onoff.sh --corpus-scope job-regressions

# Optimizer-only validation; no workload execution.
python3 auto_test/check_outeryan_dp.py --out auto_test/results/unique_optimizer_audit_sj020.json
```

`--version` is retired. `--all` is an alias for the default unique corpus.
The query timeout defaults to **600 seconds per statement**; `--timeout S` overrides it.

## Semantic filter design

[`sources/semantic_filter_design.json`](sources/semantic_filter_design.json) pins
source-query hashes, literal predicates, business meaning, denominator populations
and calibration counts. The three retained-fraction bands are **(0,5%)**,
**[5,40%)**, and **[40,80%]**. No extra >80% tier is generated.

Filters use source-style date/year/episode ranges, names/colors and categories.
They replace the complete WHERE clause, avoiding compounded filtering. No active
query uses identifier modulo or hash sampling. Source adaptations are disclosed:
these queries preserve source join skeletons and predicate styles, not the full
semantics of their original benchmark queries. SQLStorm sources without original
selection predicates receive explicitly documented business filters.

The source design starts from 34 provenance-backed seeds and five structural slots
per seed. Every distinct source-derived join SQL at all three bands remains in the
unique corpus. Mixed join labels are fixed per structure across bands. Duplicate
removal can change the original exact edge-label balance; the manifest records
actual join vectors rather than claiming preserved equal counts.

Selectivity is the fraction of base entities satisfying the predicate, including
NULLs in the denominator; it is not the final join-output fraction or the optimizer's
estimate. Frozen local calibration does not guarantee identical selectivity at
another database scale. Audit the target databases with:

```bash
python3 auto_test/gen_outerjoin_benchmark.py --audit-selectivity --audit-timeout 600
```

This performs only base-column counts and writes `results/semantic_selectivity_audit.json`.
Database paths use `GRAPH_DB`, `TPCH_DB`, `TPCDS_DB` and `JOB_DB` overrides.

## Aggregation and reporting

The 102 aggregation queries retain the source-derived structure and filters while
replacing the projection with 42 COUNT, 30 SUM, 15 MIN and 15 MAX queries. The
assignment uses structural metadata, not observed performance. The sensitivity
subset has six bases, three filter bands each, balanced over TPC-H/TPC-DS/JOB and
left-deep/right-deep/bushy shapes. Membership is recorded in the main manifest.

`gen_experiment_result.py --date YYYYMMDD` deduplicates observations by SQL identity
before eligibility filtering. The latest observation wins, including failures;
it never chooses the fastest duplicate. Original result CSVs remain unchanged.
Unresolvable SQL definitions are kept separate rather than assumed equivalent.
Plot/table labels use query type, family and shape, such as `Q-H-LD-01`, with no
version component. Overall counts include only correct measured pairs with at
least one runtime >=1 s; speed-up summaries use measured OuterYan-selected plans.

## Experimental optimizer configuration

The current **experimental** SJ weight is 0.20 and the cost ceiling is 1.20.
A fresh Release EXPLAIN audit of the 650 unique queries enters DP for all 650:
**399 choose OuterYan (61.38%)**, 155 have the same grouping as DuckDB, and 96 fail
the cost gate. This is optimizer selection coverage, not measured speed-up.
The prior conservative SJ weight 1.0 and the experimental weight 0.20 must be
reported separately. Cost-ceiling counterfactuals do not bound runtime slowdown.

## Historical reproducibility

`revisions/pre_semantic_20260925/` preserves the SQL used by older saved results.
`revisions/semantic_ranges_20260929/` preserves the definitions before this merge.
Their versioned paths are historical inputs only; `run_all.sh` never scans them.
The generator builds intermediate source expansions in a temporary directory and
emits only the unique corpus. A regeneration verifies existing managed SQL hashes
before replacing generated files. Local notes and unmanaged non-SQL files survive.
