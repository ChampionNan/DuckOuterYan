# OuterYan cost-model audit — 2026-08-18

## Scope

This audit uses:

- `results/run_all_20260818_011114.log`;
- `results/experiment_onoff_core_20260818_011114.csv` (170 rows); and
- `results/experiment_onoff_industry_inspired_20260818_011114.csv` (9 rows).

It compares the recorded V5 costs with measured T1/TM timings and traces the
cost implementation in DuckDB's `join_order/cost_model.cpp` and OuterYan's
`outer_yan_dp.cpp` / `outer_yan_optimizer.cpp`.

## What the two DP models estimate

DuckDB's stock join-order cost is:

```text
subtree_cost = left_cost + right_cost + estimated_join_cardinality
```

The stock code explicitly says that join type and join algorithm are not
considered. There is no per-outer-join `1.2` multiplier. The `1.20` value in
OuterYan is a final candidate-gate stretch ceiling, not DuckDB's join cost.

OuterYan does use the join kind. For an equality edge it estimates:

```text
inner = left_rows * right_rows / max(left_ndv, right_ndv)
unmatched_left  = left_rows  * (1 - min(1, right_ndv / left_ndv))
unmatched_right = right_rows * (1 - min(1, left_ndv / right_ndv))
```

INNER emits `inner`; LEFT/RIGHT add the unmatched rows on the preserved side;
FULL adds both. Child orientation flips LEFT and RIGHT before this calculation.
All three output weights are currently `1.0`. The two semi-join rounds are
costed separately as materialize, filter-build, replay, lookup, and emit row
work, then added once by the final gate.

## August 18 decisions

For the 170-query derived run:

| Outcome | Queries |
|---|---:|
| Structurally inapplicable | 50 |
| Same grouping as DuckDB (`DUCKDB_PLAN`) | 42 |
| Changed grouping, rejected by cost gate | 49 |
| OuterYan selected | 24 |
| Incomplete / no final decision | 5 |

The 50 `INAPPLICABLE` rows have three concrete structural causes:

| Applicability failure | Queries | Detail |
|---|---:|---|
| No outer join remained | 26 | Filter pushdown and outer-join simplification reduced the optimized skeleton to pure INNER joins, so OuterYan correctly deferred to DuckDB's ordinary join-order optimizer. |
| Join key contained an implicit cast | 13 | Four JOB 10a variants, all five JOB 20a variants, and four JOB 26a variants contained an equality such as `person_role_id = CAST(id AS DOUBLE)`. The current gate requires both equality sides to be plain column references. |
| ON clause was not one plain two-column equality | 11 | Five TPC-DS Q72 variants retained a cross-relation theta predicate; four SQLStorm TPC-DS 10809 variants retained `d_year = 2023` as a one-relation join condition; TPC-DS Q40 `rduF` retained a `BETWEEN` condition; JOB 17a `rduF` retained a `LIKE` condition. |

The 26 pure-INNER cases were all seven inapplicable TPC-H rows; eight TPC-DS
rows (`10809_rduL`, `28643_lduR`, `q40_lduR`, both Q51 mixed-deep variants,
`q80_rduL`, `q93_lduR`, and `q97_rduL`); and eleven JOB rows (`01a_lduR`,
`10a_rduL`, `11a_rduL`, `16a_lduR`, `17a_lduR`, `21a_rduL`, `26a_lduR`,
`11914_rduL`, `15596_lduR`, plus `18930_bmx` and `18930_lduR`).

The five incomplete rows were the five SQLStorm TPC-DS 11376 variants
(`bmx`, `ldmx`, `lduF`, `rdmx`, and `rduL`). Every one timed out during the
DuckDB/OFF baseline after 1,800 seconds. Consequently the harness never ran the
ON side, correctness comparison, cost decision, or phase profile; these were
timeouts, not unexplained missing decisions.

The phase figure's separate “4 incomplete selected profiles omitted” note does
not refer to those five rows. Those four queries completed correctness and
timing and selected OuterYan, but the dedicated profiling subprocess exited
with status 1 and produced no phase counters: SQLStorm TPC-H 25509 `ldmx`,
`rdmx`, and `rduF`, plus TPC-H Q08 `rdmx`.

The nine industry-pattern rows added four cost rejections, one same grouping,
two aggregate bypasses, and two OuterYan selections. Across both CSVs, 26
queries selected OuterYan: 13 TM wins and 13 TM regressions. Their TM geometric
mean was `0.843x`. The worst result was
`ojb_tpcds_q93_return_reason_rduF` at `0.018x`; it entered through the V5
`1.35` stretch tier with a recorded raw cost ratio of `1.320`.

The strict gate also admitted regressions because V5 discounted the modeled
semi-join work by `0.50`. Examples include TPC-H Q08 variants (`0.174x` and
`0.196x`) and JOB 21a deep variants (`0.693x` and `0.712x`). The failures are
not explained by outer joins being treated as `inner * 1.2`; that is not the
implemented model. They show that the semi-join discount was too optimistic
for the new derived workload and that output-cardinality work alone cannot
fully model row width, hash construction, cache behavior, or parallel
contention.

## V6 adjustment

V6 makes two conservative source-level changes:

```text
SEMIJOIN_COST_RATIO:                         0.50 -> 1.00
STRETCH_MAX_CANDIDATE_TO_BASELINE_RATIO:     1.35 -> 1.20
```

Replaying all 79 changed-grouping August rows with the recorded cost components
selects 14 strict-gate candidates and no stretch candidates. All 14 were in the
previously selected set, so their measured timing is available: 9 TM wins, 5
TM regressions, TM geometric mean `1.312x`, and worst result `0.488x`. This
removes the `0.018x` stretch failure and the largest reducer-dominated strict
failures. It does not claim perfect prediction; the remaining TPC-H regressions
demonstrate missing physical signals that should be addressed with a broader
forced-candidate training/validation set rather than benchmark-family-specific
constants.

The replay is deterministic because these two constants affect only final
candidate selection, not OuterYan DP enumeration. A release rerun of the
unified corpus is still required before drawing final performance conclusions.

## TPC-H and TPC-DS selection rate

The low selection rate should not be corrected by simply loosening the gate.
In the recorded V5 run, TPC-H selected OuterYan for 7 of 49 completed queries;
all seven regressed on TM, with a `0.457x` geometric mean. TPC-DS selected 2 of
55 completed queries: one was a small `1.016x` win and the other was the
`0.018x` stretch-gate failure. Replaying the V6 gate selects four TPC-H rows,
all measured regressions (`0.593x` geometric mean), and no TPC-DS rows. The low
V6 rate is therefore conservative behavior supported by the available timing
data, not evidence that the threshold should be raised.

The safer adjustment path is:

1. Change generated variants whose NULL-rejecting filters erase every outer
   join, so at least one genuine outer join reaches the applicability gate.
2. Add safe support for child-local ON predicates and lossless casted equality
   keys. Cross-relation theta residuals still require explicit semantic and DP
   support and should not be silently treated as ordinary equality edges.
3. Extend the cost model with physical signals missing from row-count cost:
   payload width/bytes, hash-table construction and lookup work, reducer replay
   volume, and the parallel critical path rather than aggregate CPU work alone.
4. Collect a focused release-mode forced-candidate sample for currently
   cost-rejected TPC-H and TPC-DS rows. Their OuterYan runtime is not present in
   this ON/OFF run because the enabled optimizer correctly executed DuckDB's
   selected plan, so rejected rows cannot be used to calibrate a looser gate.

No family-specific multiplier is recommended; it would tune to benchmark names
rather than the physical properties responsible for the regressions.
