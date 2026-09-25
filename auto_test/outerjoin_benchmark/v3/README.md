# OuterJoin benchmark v3

V3 adds deterministic root-aggregation coverage without selecting queries by
observed performance.

- 34 source-derived seeds: TPC-H 5, TPC-DS 7, JOB 10, SQLStorm 12.
- Three mixed-join structural variants per seed: left-deep, right-deep, and a
  third bushy/alternate shape.
- Four aggregate operators in three semantic classes: 42 global `COUNT(*)`, 30
  grouped `SUM`, and one 30-query extremum class split equally into 15 grouped
  `MIN` and 15 grouped `MAX` queries. A fixed weighted schedule gives every one
  of the three structural slots the same 14/10/5/5 operator mix; no measured
  result affects the assignment. Group and aggregate keys are distinct join-key
  references.
- 102 active queries in `benchmark/`.
- Balanced input join labels across 375 edges: I/L/R/F = 94/94/94/93.
- 42 separately reported selectivity-stress queries in
  `selectivity_stress/`: six paired mixed-join bases times seven selectivity
  tiers (0.025%, 0.05%, 0.2%, 10%, 20%, 50%, and 80%).

Supported root aggregates enter the normal OuterYan candidate pipeline. They use
a conservative 0.90 candidate/baseline cost ceiling with no relaxed tier.
Aggregate pushdown runs only when that gate selects OuterYan; otherwise the
exact DuckDB baseline is executed. `MIN` and `MAX` are separate queries so each
pushed annotation has one unambiguous aggregate meaning. Grouped `MIN`, `MAX`,
and `SUM` exercise aggregate pushdown; global `COUNT(*)` exercises the same
selection and semi-join pipeline but keeps the count above the joins to preserve
outer-join NULL-padding semantics.

The selectivity-stress scope is deliberately compact and is not part of the
102-query headline aggregate set. Its six bases are selected from static v2
metadata, never from measured speed-up: two each from TPC-H, TPC-DS, and JOB,
and two each of left-deep, right-deep, and bushy shape across the complete set.
Each execution family contributes one native benchmark source and one
SQLStorm-derived source, so TPC-H, TPC-DS, JOB, and SQLStorm provenance all
remain represented.
Each base appears at all seven levels, so the result is a paired sensitivity
curve rather than 42 independent workload samples. The deterministic hash
predicate controls experimental sampling; it does not by itself claim a
stats-backed cardinality estimate for the optimizer cost gate.

```bash
python3 auto_test/gen_outerjoin_benchmark.py --version v3
# Both v3 components (102 aggregation + 42 selectivity-stress queries)
bash auto_test/experiment_onoff.sh --version v3 --only all

# Aggregation component only
bash auto_test/experiment_onoff.sh --version v3 \
  --corpus-scope benchmark --only all

# Selectivity-stress component only
bash auto_test/experiment_onoff.sh --version v3 \
  --corpus-scope selectivity-stress --only all

# v1/v2/v3 benchmarks, then this v3 stress scope; this is also the default
bash auto_test/experiment_onoff.sh --all
```
