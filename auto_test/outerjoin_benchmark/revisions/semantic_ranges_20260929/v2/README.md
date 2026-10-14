# OuterJoin benchmark v2

V2 is the expanded workload. V1 remains the default harness corpus.

- 510 benchmark-derived queries: 170 mixed-join source structures at
  three semantic retention bands: (0,5%), [5,40%), and [40,80%].
- 54 Graph, industry, and schema-synthetic controls, relabeled
  with deterministic mixed join vectors while retaining their relation graph.
- 564 active queries in `benchmark/`.
- Two mixed counterparts of historical v1 JOB regressions in
  `job_regressions/`; both require fresh v2 measurement.

Each v2 query replaces the complete v1 filter with one business range. Calendar
intervals, release years, episode ranges, name/color patterns and categories follow
the source query conventions;
no modulo/hash predicate or old strong prefilter is retained. Literals and
base-population calibration counts are pinned in
[`../sources/semantic_filter_design.json`](../sources/semantic_filter_design.json).
See [the selectivity design](../README.md#semantic-selectivity-design-2026-09-29)
for band definitions, NULL handling, calibration scope and count-audit commands.

## Join-type design

V2 uses the same deterministic mixed-join design as the current v1: a blocked
rotation over INNER, LEFT, RIGHT, and FULL. Each of the 34 source queries contributes
five shapes. A base shape uses one join vector at all three selectivity tiers,
so selectivity comparisons do not also change join semantics. Across the 170
base structures, the 625 join edges are distributed as 157 INNER and 156 each
LEFT, RIGHT, and FULL. Family/shape strata differ by at most three edges per
kind. Queries with at least four edges contain all four kinds; shorter queries
contain mixed two- or three-kind slices. This intentionally includes both
all-outer (`L/R/F`) cases and cases that mix INNER with outer joins, but no v2
main query is an all-FULL or other single-kind vector.
The counts apply to the SQL input expression. They do not assert that every
label survives logical simplification or maps one-to-one to a physical join.

The 54 retained controls use the same balancing objective without changing
their relations, equality predicates, or parentheses; their WHERE filters use the same semantic design. Across the complete 564
queries, the 2,051 join edges contain 512 INNER, 513 LEFT, 513 RIGHT, and 513
FULL labels. There are 75 all-outer queries and 489 that contain INNER plus outer
joins.

Every structural-core query retains the relation instances and connected
equality graph of a pinned TPC-H, TPC-DS, JOB, or SQLStorm source query. The
25 Graph controls, nine industry controls, and 20 schema-synthetic controls are
retained as explicitly labeled control strata; they are not described as
source-derived benchmark queries. The complete Graph suite contains 10 bushy,
seven left-deep, and eight right-deep expressions and is included without
timing-based selection.

`v1_advantage_hypothesis` identifies star/branch cases with alternate, bushy,
or right-start groupings motivated by the 0916 observations. It is an analysis
tag, not an inclusion rule. Every seed and tree variant is generated at every
tier, and `paired_structural_control` cases remain in the same workload.

The compact paired selectivity-stress ablation has moved to v3. V2 remains its
source of mixed-join structures and semantic range variants, but no longer
owns a separate stress directory.

The JOB guard suite contains mixed-v2 counterparts of two queries that were
below the objective 0.95x threshold in the retired FULL-heavy revision:
`ojb_sqlstorm_job_11914_bdmx` and
`oy_jb_jb_bushy4a_v2`. They remain in the main benchmark;
the focused copies are not additional samples. Since their join labels have
changed, the historical values are not v2 measurements, and the manifest marks
both counterparts `requires_v2_remeasurement`.

```bash
python3 auto_test/gen_outerjoin_benchmark.py --version v2
bash auto_test/experiment_onoff.sh --version v2 --only all
bash auto_test/experiment_onoff.sh --all  # v1/v2/v3, then v3 selectivity-stress

# Focused JOB regression guard (2 queries).
bash auto_test/experiment_onoff.sh --version v2 \
  --corpus-scope job-regressions --only job
```
