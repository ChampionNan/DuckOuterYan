# OuterJoin benchmark v2

V2 is the expanded workload. V1 remains the default harness corpus.

- 510 benchmark-derived queries: 170 mixed-join source structures at
  deterministic hash-filter tiers of approximately 0.1%, 1%, and 5%.
- 36 Graph, industry, and schema-synthetic controls, relabeled
  with deterministic mixed join vectors while retaining their relation graph.
- 546 active queries in `benchmark/`.
- 84 balanced-tier, metadata-selected selectivity-ablation queries in
  `selectivity_stress/`. These are explicitly **not** headline-eligible.
- Two mixed counterparts of historical v1 JOB regressions in
  `job_regressions/`; both require fresh v2 measurement.

The 5% upper tier is intentionally conservative. Each v2 core query adds its
hash predicate to the source-derived filter. The `manifest.csv` fields record
the source query, structural transformation, anchor column, tier, modulus,
join vector, and pattern role.

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

The 36 retained controls use the same balancing objective without changing
their relations, equality predicates, or parentheses. Across the complete 546
queries, the 2,003 join edges contain 501 INNER, 501 LEFT, 501 RIGHT, and 500
FULL labels. Sixty-seven queries are all-outer and 479 contain INNER plus outer
joins.

Every structural-core query retains the relation instances and connected
equality graph of a pinned TPC-H, TPC-DS, JOB, or SQLStorm source query. The
seven Graph controls, nine industry controls, and 20 schema-synthetic controls
are retained as explicitly labeled control strata; they are not described as
source-derived benchmark queries.

`v1_advantage_hypothesis` identifies star/branch cases with alternate, bushy,
or right-start groupings motivated by the 0916 observations. It is an analysis
tag, not an inclusion rule. Every seed and tree variant is generated at every
tier, and `paired_structural_control` cases remain in the same workload.

The separate selectivity-stress suite starts from 12 mixed v2 counterparts of
feasibility-screened v1 source-derived structures, selected without measured
speed. Its static target domain is
mixed joins with at least four relations and an applicable null-rejecting
predicate. It uses four distinct source queries from each of TPC-H, TPC-DS,
and JOB. Within every family, the first three slots cover left-deep, right-deep,
and bushy trees; the fourth favors a new source benchmark and greater
relation-count separation. Ties are resolved by a fixed salted SHA-256 rank
over query identifiers, so regeneration never reads result files. Each
structure is evaluated at approximately 0.025%, 0.05%,
0.2%, 10%, 20%, 50%, and 80% target selectivity. Every tier therefore contains
exactly 12 queries. A common 4,000-bucket hash predicate produces nested,
deterministic samples. This is balanced representation across seven
predeclared tiers, not a claim that the numerical selectivity values or
realized output cardinalities are uniformly distributed. Because the seven
variants of a base are correlated, this ablation is reported separately from
the 546-query benchmark. The manifest records the source hashes, selection
rule, `performance_selected=false`, and `headline_eligible=false`.

The JOB guard suite contains mixed-v2 counterparts of two queries that were
below the objective 0.95x threshold in the retired FULL-heavy revision:
`ojb_sqlstorm_job_11914_bdmx` (historically 0.772x) and
`oy_jb_jb_bushy4a_v2` (historically 0.857x). They remain in the main benchmark;
the focused copies are not additional samples. Since their join labels have
changed, the historical values are not v2 measurements, and the manifest marks
both counterparts `requires_v2_remeasurement`.

```bash
python3 auto_test/gen_outerjoin_benchmark.py --version v2
bash auto_test/experiment_onoff.sh --corpus-version v2 --only all
bash auto_test/experiment_onoff.sh --all  # v1, then v2

# Separately reported selectivity ablation (84 queries).
bash auto_test/experiment_onoff.sh --corpus-version v2 \
  --corpus-scope selectivity-stress --only all

# Focused JOB regression guard (2 queries).
bash auto_test/experiment_onoff.sh --corpus-version v2 \
  --corpus-scope job-regressions --only job
```
