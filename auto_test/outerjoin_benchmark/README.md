# Frozen outer-join workload

The active `benchmark/` directory contains 321 SQL definitions: SGPB/Graph 67,
TPC-H 86, TPC-DS 61, and JOB 107. The manifest specifies identities, hashes,
join structures, predicates, datasets, and configuration thresholds.

This workload was curated using historical performance observations. The source
artifact retains selection rules, query identities, and reasons, without the
underlying experimental outputs. Membership must not be represented as an
independently selected evaluation sample. Regeneration applies frozen decisions;
it neither reads timing results nor searches for a target performance number.

The current membership keeps 282 historically selected OuterYan queries and
39 non-three-relation cost-rejected controls. TPC-DS controls were reduced from
42 to 16 on 2026-10-15, retaining one per source pattern and tree shape, balancing
tiers with a deterministic query-ID tie-break and no runtime ranking. This is
workload-level deduplication, not proof of equal optimized join groupings.
This control deduplication leaves selected membership and other families unchanged. Twenty-one cases with both engines
timed out are removed; four DuckDB-only timeout cases are retained. The six selected three-relation
queries are retained. The 720-query predecessor is recoverable under
`revisions/pre_plan_cohort_20261014/benchmark/`; the frozen policy is
`sources/plan_cohort_20261014.json`. `benchmark/plan_cohort.csv` distinguishes
selected queries from cost controls using historical decisions, not new timings.
`sources/cohort_selectivity_20261015.json` pins two further predicate-only
updates (TPC-H SQLStorm 25509 bushy COUNT and JOB SQLStorm 11914 bushy COUNT),
with exact CPU9 observation identities. The TPC-H update changes its tier from
high to medium. Those updates preserve counts; the JOB 10a right-deep COUNT
query was subsequently retired by explicit user request after its measured
speedup remained below 0.7x. The minimum-speedup TPC-H and JOB queries were also
retired on 2026-10-15 by explicit request: `th_real_custdist` left-deep high and
SQLStorm 11914 bushy high COUNT. The latter's predicate update remains recoverable
from the pinned definition but is not generated into the active workload.
These outcome-conditioned choices do not guarantee a future 0.7x lower bound.
Unpromoted tuning and grouping alternatives are retired from the source artifact.

The cohort reporting rule uses a 1x policy default for unexecuted DuckDB fallbacks
and a 600-second DuckDB timeout proxy when OuterYan completed. It does not replace
raw observations or remove timeout flags. See `report_plan_cohort.py` in the
harness guide for the separate derived statistics; measured-only results remain
available alongside the capped results.

- `sources/`: source SQL, licenses, predicate definitions, and frozen policies.
- `revisions/`: archived SQL and manifests needed for reconstruction and checks.
- `candidates/`: only the 20 pinned TPC-H SQL inputs and two mappings required for reconstruction.
- `graph_dataset_retest/`: dataset-qualified SQL and input manifests.

From the repository root, run `python3 auto_test/gen_outerjoin_benchmark.py` to
regenerate. The SQL definitions are unchanged by anonymous packaging.

Manifests, source hashes, query lists, and policy thresholds are necessary inputs.
Measured runtimes, speedups, correctness records, profiles, local pilot reports,
and manuscript results belong under ignored `auto_test/results/`. There are no
exceptions for selected cases. See [the harness guide](../README.md) for execution.
