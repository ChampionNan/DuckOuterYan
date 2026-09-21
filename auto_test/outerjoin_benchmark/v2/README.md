# OuterJoin benchmark v2

V2 is the expanded workload. V1 remains the default harness corpus.

- 510 benchmark-derived queries: all 170 v1 core structures at deterministic
  hash-filter tiers of approximately 0.1%, 1%, and 5%.
- 32 timeout-filtered v1 evaluation controls.
- 542 active queries in `benchmark/`.
- 84 balanced-tier, metadata-selected selectivity-ablation queries in
  `selectivity_stress/`. These are explicitly **not** headline-eligible.
- Two confirmed JOB regressions in `job_regressions/` for fast focused retests.

The 5% upper tier is intentionally conservative. Each v2 core query adds its
hash predicate to the v1 filter, so the expanded workload never makes the v1
input less selective. The `manifest.csv` fields record the source query,
structural transformation, anchor column, tier, modulus, and pattern role.

`v1_advantage_hypothesis` identifies star/branch cases with alternate, bushy,
or right-start groupings motivated by the 0916 observations. It is an analysis
tag, not an inclusion rule. Every seed and tree variant is generated at every
tier, and `paired_structural_control` cases remain in the same workload.

The separate selectivity-stress suite starts from 12 v1 benchmark-derived core
structures selected without measured performance. Its static target domain is
all-FULL joins with at least four relations and an applicable null-rejecting
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
the 542-query benchmark. The manifest records the source hashes, selection
rule, `performance_selected=false`, and `headline_eligible=false`.

The JOB regression suite pins the two OuterYan-selected 0916 cases below the
objective 0.95x threshold: `ojb_sqlstorm_job_11914_bdmx` (0.772x) and
`oy_jb_jb_bushy4a_v2` (0.857x). They remain in the main benchmark; the focused
copies are not additional samples. Removing them only because they are slow
would bias the benchmark.

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
