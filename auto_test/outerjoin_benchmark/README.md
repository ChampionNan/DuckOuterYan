# Frozen outer-join workload

The active `benchmark/` directory contains 350 SQL definitions: SGPB/Graph 67,
TPC-H 87, TPC-DS 87, and JOB 109. The manifest specifies identities, hashes,
join structures, predicates, datasets, and configuration thresholds.

This workload was curated using historical performance observations. The source
artifact retains selection rules, query identities, and reasons, without the
underlying experimental outputs. Membership must not be represented as an
independently selected evaluation sample. Regeneration applies frozen decisions;
it neither reads timing results nor searches for a target performance number.

The current membership keeps 285 historically selected OuterYan queries and
65 non-three-relation cost-rejected controls. Twenty-one cases with both engines
timed out are removed; four DuckDB-only timeout cases are retained. The six selected three-relation
queries are retained. The 720-query predecessor is recoverable under
`revisions/pre_plan_cohort_20261014/benchmark/`; the frozen policy is
`sources/plan_cohort_20261014.json`. `benchmark/plan_cohort.csv` distinguishes
selected queries from cost controls using historical decisions, not new timings.
Same-grouping alternatives in `candidates/grouping_20261014/` are independent,
unpromoted queries with changed join-type assignments. They are not part of 350.

The cohort reporting rule uses a 1x policy default for unexecuted DuckDB fallbacks
and a 600-second DuckDB timeout proxy when OuterYan completed. It does not replace
raw observations or remove timeout flags. See `report_plan_cohort.py` in the
harness guide for the separate derived statistics; measured-only results remain
available alongside the capped results.

- `sources/`: source SQL, licenses, predicate definitions, and frozen policies.
- `revisions/`: archived SQL and manifests needed for reconstruction and checks.
- `candidates/`: prepared alternative queries and input mappings.
- `graph_dataset_retest/`: dataset-qualified SQL and input manifests.

From the repository root, run `python3 auto_test/gen_outerjoin_benchmark.py` to
regenerate. The SQL definitions are unchanged by anonymous packaging. Use
`--audit-selectivity` to verify predicate bands against existing local databases;
the resulting audit is an ignored output, not a source definition.

Manifests, source hashes, query lists, and policy thresholds are necessary inputs.
Measured runtimes, speedups, correctness records, profiles, local pilot reports,
and manuscript results belong under ignored `auto_test/results/`. There are no
exceptions for selected cases. See [the harness guide](../README.md) for execution.
