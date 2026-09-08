# PostgreSQL outer-join DP trace report

## Result

PostgreSQL does not reassociate a `FULL OUTER JOIN` that survives preprocessing.
It turns every FULL node into a nested two-item planning subproblem before the
bottom-up join DP runs.  Therefore a plan on the other side of that FULL
boundary is normally **not proposed**, rather than proposed and rejected by
`join_is_legal()`.

The local PostgreSQL 16.2 source was instrumented without changing planner
decisions.  The logging is gated by the postmaster environment variable
`PG_OJ_TRACE=1` and emits `NOTICE` records from:

- `src/backend/optimizer/plan/initsplan.c`: FULL barriers, construction and
  append order of every `SpecialJoinInfo`, and every minimum-set update;
- `src/backend/optimizer/path/joinrels.c`: every DP level, pair-generator gate,
  proposed pair, relevant pure-outer-join legality outcome, outer-join relid
  addition, and before/after path-list count.

Stock PostgreSQL has no flag that exposes these search-space events;
`EXPLAIN` and `debug_print_plan` expose only the selected plan.  The relevant
design is also present on current PostgreSQL `master`: the
[optimizer README](https://github.com/postgres/postgres/blob/master/src/backend/optimizer/README#L215-L228)
states that FULL joins are not reordered, and
[`deconstruct_recurse()`](https://github.com/postgres/postgres/blob/master/src/backend/optimizer/plan/initsplan.c#L1740-L1748)
creates the nested FULL-join subproblem. The DP and restriction code is in
[`join_search_one_level()` / `join_is_legal()`](https://github.com/postgres/postgres/blob/master/src/backend/optimizer/path/joinrels.c#L60-L518),
with synthetic OJ-ID maintenance in
[`add_outer_joins_to_relids()`](https://github.com/postgres/postgres/blob/master/src/backend/optimizer/path/joinrels.c#L739-L829).

## Reading the trace

The trace is emitted by research-only `OJTRACE` calls; it is not a PostgreSQL
GUC and it does not change planner state.  Bitmap sets use PostgreSQL's
`bmsToString()` format: `(b)` is empty and `(b 1 2)` is `{1,2}`.

| Event | Meaning |
|---|---|
| `FULL_BARRIER` | `deconstruct_recurse()` made a nested two-item joinlist. Cross-boundary pairs will not enter the same DP problem. |
| `SJI_BEGIN` | Start building one `SpecialJoinInfo`; `previous_sji_count` is the number of syntactically lower SJIs already available. |
| `MIN_INIT` | Initial `minL/minR`, clause relids, strict relids, and `lhs_strict`. |
| `MIN_SCAN` / `MIN_RULE` | Loop over one older SJI and apply a preservation, FULL-barrier, PHV, or identity-3 rule. |
| `COMMUTE_PRUNE` | Remove tentative commute IDs that an intervening restriction added back to a minimum set. |
| `COMMUTE_BACKPATCH` | Write the reciprocal `commute_above_*` ID into the lower SJI. |
| `SJI_FINAL` / `SJI_APPEND` | Final constraint and its bottom-up position in `root->join_info_list`. A later `COMMUTE_BACKPATCH` can still update an older entry's `commute_above_*` field. |
| `DP_LEVEL_BEGIN` / `DP_INITIAL` | Start one DP level and list that joinlist subproblem's initial items. `level` counts joinlist items, not necessarily all base tables in the SQL query. |
| `PAIR_GATE` | A pair examined by `join_search_one_level()`: overlap, relevant-clause, and join-order-restriction tests decide `PROPOSE` or `SKIP`. |
| `PAIR_PROPOSE` | `make_join_rel()` received this pair. Absence of this record means the pair was never enumerated. |
| `LEGAL_BEGIN` | Reset per-proposal state: `match=NONE`, `reversed=0`, `uniqueified=0`, and `must_left=0`. |
| `LEGAL_SCAN` | Loop over one SJI in bottom-up append order. |
| `LEGAL_SKIP` | This SJI is irrelevant or already completed; this is not rejection of the pair. |
| `LEGAL_MATCH` | The two inputs contain this SJI's `minL` and `minR`; this SJI determines join kind and orientation. |
| `LEGAL_STATE` | Record a condition that must be satisfied after later SJIs are scanned, such as `must_be_leftjoin`. |
| `LEGAL_REJECT` / `LEGAL_ACCEPT` | Final legality decision for the proposed pair. |
| `ADD_OJ_*` | Add, withhold, or cascade synthetic OJ relids after a legal join. `ADD_OJ_DECISION` exposes every cascade prerequisite. |
| `PAIR_RESULT` | Legality/canonicalization result. `accepted=1 stage=LEGAL_CANONICAL` is emitted before `build_join_rel()` and does **not** prove that a path survived. |
| `PATH_RESULT` | Reports either a dummy-rel skip or the canonical joinrel's path-list counts before and after population. Equal counts can mean pruning or replacement, not that nothing was tried. |
| `DP_LEVEL_RESULT` / `DP_LEVEL_END` | Canonical join relations produced at this level. One relation can contain paths from several association trees. |

`PAIR_GATE` preserves PostgreSQL's short-circuit evaluation order. Therefore
`restriction=0` means an evaluated false only when `overlap=0` and `clause=0`;
when `clause=1`, the restriction test was not needed and the initialized zero
means “not evaluated.” The decisive `{A,C}` record has `overlap=0, clause=0`,
so its `restriction=0` is an actual evaluated false.

The most important distinction is:

```text
PAIR_GATE action=SKIP       = pair generator examined it but did not propose it
PAIR_PROPOSE + LEGAL_REJECT = enumerated, then rejected by restrictions
no PAIR_GATE                = pair was not visited by these generator loops
```

For the FULL witness, the two `DP_INITIAL` lists and `FULL_BARRIER` records
show why `{B,C}` has no gate: `B` and `C` are never initial items in the same
DP subproblem. In general, use those context records before interpreting the
absence of a gate, since higher-level generator prefilters can also skip work.

`join_is_legal()` is also used by a join-clause heuristic.  For these witnesses,
the actual enumeration calls are the `LEGAL_*` blocks immediately following a
`PAIR_PROPOSE`; the report does not claim that every possible semijoin or
lateral early return has been instrumented.

## Worked DP example: LEFT/LEFT identity 3

This is the smallest example that shows PostgreSQL actively using an outer
join identity, rather than merely preserving the written order:

```sql
SELECT a.k, b.k, c.k
FROM (a LEFT JOIN b ON a.k = b.k)
LEFT JOIN c ON b.k = c.k;
```

PostgreSQL 16.2 assigned these bitmap IDs in the observed trace:

```text
1=A, 2=B, 3=O1(A LEFT B), 4=C, 5=O2(the upper LEFT)
```

`b.k=c.k` is strict for `B`, so identity 3 is valid:

```text
(A LEFT_Pab B) LEFT_Pbc C
=
A LEFT_Pab (B LEFT_Pbc C)
```

### Step 0: build the SJIs bottom-up

The lower join produces:

```text
PGOJ SJI_BEGIN oj=3 type=LEFT synL=(b 1) synR=(b 2)
PGOJ MIN_INIT oj=3 clause=(b 1 2) strict=(b 1 2)
     lhs_strict=1 minL=(b 1) minR=(b 2)
PGOJ SJI_FINAL oj=3 type=LEFT minL=(b 1) minR=(b 2)
PGOJ SJI_APPEND position=1 oj=3 ...
```

For the upper join, `B` is nullable above `O1`, so the upper reference to
`b.k` carries `varnullingrels={O1}`.  Consequently `pull_varnos()` returns
`{B,O1,C}` and initial `minL` is `{B,O1}`:

```text
PGOJ SJI_BEGIN oj=5 type=LEFT
     synL=(b 1 2 3) synR=(b 4) previous_sji_count=1
PGOJ MIN_INIT oj=5 clause=(b 2 3 4) strict=(b 2 4)
     lhs_strict=1 minL=(b 2 3) minR=(b 4)
PGOJ MIN_SCAN current_oj=5 lower_oj=3 lower_type=LEFT ...
PGOJ MIN_RULE current_oj=5 rule=IDENTITY3_COMMUTE side=L
     lower_oj=3 minL=(b 2) tentative_belowL=(b 3)
PGOJ COMMUTE_PRUNE current_oj=5 minL=(b 2) minR=(b 4)
     belowL=(b 3) belowR=(b)
PGOJ COMMUTE_BACKPATCH current_oj=5 lower_oj=3 side=L
     lower_aboveL=(b 5)
PGOJ SJI_FINAL oj=5 type=LEFT minL=(b 2) minR=(b 4)
     belowL=(b 3) belowR=(b) lhs_strict=1
```

The resulting identity-3 state is:

```text
S2.minL:             {B,O1} -> {B}
S2.commute_below_l:  {}     -> {O1}
S1.commute_above_l:  {}     -> {O2}
S2.lhs_strict:       true      (precomputed enabling condition)
```

Deleting `O1` from `S2.minL` makes `{B} LEFT {C}` match `S2`; the commute
fields preserve correct nulling-relid semantics if that alternative is used.

### Level 1

The current joinlist is flat because both operators are LEFT joins:

```text
joinrels[1] = { {A}, {B}, {C} }
trace IDs   = { (b 1), (b 2), (b 4) }
```

### DP level 2

The pair generator examines all three unordered level-2 pairs.  It proposes
exactly two. `{A,C}` has neither a relevant join clause nor a join-order
restriction, so it is explicitly gated out before `make_join_rel()`:

```text
PGOJ PAIR_GATE level=2 source=LEFT_RIGHT
     rel1=(b 1) rel2=(b 4) overlap=0 clause=0 restriction=0 action=SKIP
```

| Proposal | Loop over SJIs | Legality state | OJ-relid result |
|---|---|---|---|
| `{A}+{B}` | `S1`: normal LEFT match. `S2`: `NO_RHS_OVERLAP`. | `match=S1`, `reversed=0`, `uniqueified=0`, `must_left=0`; accept. | Add `O1`: `{A,B,O1}`. `S1.aboveL={O2}` is scanned, but `S2.minR={C}` is absent, so no cascade. |
| `{B}+{C}` | `S1`: candidate crosses its RHS, so set `must_left=1`. `S2`: normal LEFT match. | `match=S2`, `lhs_strict=1`, so the deferred must-be-strict-LEFT test passes; accept. | Withhold `O2`, because `S2.belowL={O1}` is not contained in `{B,C}`. Canonical result remains `{B,C}`. |

The corresponding observed records are:

```text
PGOJ PAIR_PROPOSE level=2 rel1=(b 1) rel2=(b 2) union=(b 1 2)
PGOJ LEGAL_MATCH candidate=(b 1 2) oj=3 orientation=NORMAL type=LEFT
PGOJ LEGAL_SKIP candidate=(b 1 2) oj=5 reason=NO_RHS_OVERLAP
PGOJ LEGAL_ACCEPT candidate=(b 1 2) oj=3 type=LEFT ...
PGOJ ADD_OJ_STEP action=ADD_OWN_OJ oj=3 result=(b 1 2 3)
PGOJ PAIR_RESULT level=2 canonical=(b 1 2 3)
     accepted=1 stage=LEGAL_CANONICAL ...
PGOJ PATH_RESULT level=2 canonical=(b 1 2 3)
     rel1=(b 1) rel2=(b 2) action=POPULATE
     pathlist_before=0 pathlist_after=1

PGOJ PAIR_PROPOSE level=2 rel1=(b 2) rel2=(b 4) union=(b 2 4)
PGOJ LEGAL_STATE candidate=(b 2 4) oj=3 action=SET_MUST_BE_LEFT
PGOJ LEGAL_MATCH candidate=(b 2 4) oj=5 orientation=NORMAL type=LEFT
PGOJ LEGAL_ACCEPT candidate=(b 2 4) oj=5 type=LEFT must_left=1
PGOJ ADD_OJ_END action=WITHHOLD_PUSHED_DOWN_OJ
     oj=5 required_belowL=(b 3) result=(b 2 4)
PGOJ PAIR_RESULT level=2 canonical=(b 2 4)
     accepted=1 stage=LEGAL_CANONICAL ...
PGOJ PATH_RESULT level=2 canonical=(b 2 4)
     rel1=(b 2) rel2=(b 4) action=POPULATE
     pathlist_before=0 pathlist_after=1

PGOJ DP_LEVEL_RESULT level=2 relids=(b 1 2 3)
PGOJ DP_LEVEL_RESULT level=2 relids=(b 2 4)
```

Therefore:

```text
joinrels[2] = { {A,B,O1}, {B,C} }
```

### DP level 3

PostgreSQL completes both association trees:

| Proposal | Loop over SJIs | Legality state | OJ-relid result |
|---|---|---|---|
| `{A,B,O1}+{C}` | `S1`: `ALREADY_DONE_IN_REL1`. `S2`: normal match. | `match=S2`, `reversed=0`; accept. | `O1` is present, so add `O2` directly. This is the written `(A LEFT B) LEFT C` path. |
| `{B,C}+{A}` | `S1`: reversed match. `S2`: its minimum sides are already in `{B,C}`, so `ALREADY_DONE_IN_REL1`. | `match=S1`, `reversed=1`; accept. | Add `O1`; then `S1.aboveL={O2}` finds all of `S2.minL`, `S2.minR`, and `S2.belowL`, so cascade `O2`. `pushed_down_count=1`. This is `A LEFT (B LEFT C)`. |

Observed records for the reassociated path are:

```text
PGOJ PAIR_PROPOSE level=3 rel1=(b 2 4) rel2=(b 1)
     union=(b 1 2 4)
PGOJ LEGAL_MATCH candidate=(b 1 2 4) oj=3
     orientation=REVERSED type=LEFT
PGOJ LEGAL_SKIP candidate=(b 1 2 4) oj=5
     reason=ALREADY_DONE_IN_REL1
PGOJ LEGAL_ACCEPT candidate=(b 1 2 4) oj=3
     type=LEFT reversed=1
PGOJ ADD_OJ_STEP action=ADD_OWN_OJ oj=3 result=(b 1 2 3 4)
PGOJ ADD_OJ_DECISION current_oj=3 target_oj=5 action=CASCADE
     already_present=0 minL_ready=1 minR_ready=1 belowL_ready=1
PGOJ ADD_OJ_STEP action=CASCADE_COMPLETED_OJ oj=5
     result=(b 1 2 3 4 5)
PGOJ PAIR_RESULT level=3 canonical=(b 1 2 3 4 5)
     accepted=1 stage=LEGAL_CANONICAL oj=3 reversed=1 pushed_down_count=1
PGOJ PATH_RESULT level=3 canonical=(b 1 2 3 4 5)
     rel1=(b 1) rel2=(b 2 4) action=POPULATE
     pathlist_before=1 pathlist_after=1
```

Both level-3 proposals call path population on the same canonical `RelOptInfo`.
The written association changes its path-list count from `0` to `1`; the
reassociated call leaves the count at `1`, because PostgreSQL's `add_path()`
prunes or replaces dominated alternatives as it goes.  The count is therefore
not an inventory of all generated physical paths.  PostgreSQL then costs the
surviving paths normally.  In this actual run its final plan is the
reassociated tree, proving that the second association survived:

```text
Merge Left Join                    -- A LEFT (B LEFT C)
  -> Seq/Sort A
  -> Merge Left Join               -- B LEFT C
       -> Seq/Sort B
       -> Seq/Sort C
```

This example is the complete bottom-up algorithm in miniature:

```text
syntax -> SJI minimum sets -> identity rule -> pair generation
       -> per-pair/per-SJI legality loop -> OJ-ID bookkeeping
       -> canonical joinrel -> path pruning and cost selection
```

## All-FULL case: PostgreSQL misses the cheaper grouping

Use a data family that performs real null extension:

```text
A: N copies of k=1 and N copies of k=2
B: N copies of k=1
C: one copy of k=1
```

The written query is:

```sql
SELECT a.k, b.k, c.k
FROM (a FULL JOIN b ON a.k=b.k)
FULL JOIN c ON b.k=c.k;
```

PostgreSQL emits two barriers before DP:

```text
PGOJ FULL_BARRIER oj=3 left=(b 1) right=(b 2)
     action=MAKE_NESTED_SUBPROBLEM
PGOJ FULL_BARRIER oj=5 left=(b 1 2 3) right=(b 4)
     action=MAKE_NESTED_SUBPROBLEM
```

Both SJIs take their complete syntactic sides as minimums and return without
testing identity rules:

```text
S1: FULL, minL={A},      minR={B}, oj=O1
S2: FULL, minL={A,B,O1}, minR={C}, oj=O2
commute_below_* = commute_above_* = {}
```

The entire normal proposal stream is consequently two independent level-2
problems:

| DP subproblem | Only proposal | SJI loop | Result |
|---|---|---|---|
| Lower FULL | `{A}+{B}` | Match `S1`; `S2` has no RHS overlap. | Add non-LEFT OJ ID `O1`: `{A,B,O1}`. |
| Upper FULL | `{A,B,O1}+{C}` | `S1` already done; match `S2`. | Add `O2`: `{A,B,C,O1,O2}`. |

The complete pair/path skeleton observed for the query is:

```text
PGOJ DP_LEVEL_BEGIN level=2 initial_count=2
PGOJ DP_INITIAL slot=1 relids=(b 1)
PGOJ DP_INITIAL slot=2 relids=(b 2)
PGOJ PAIR_GATE level=2 rel1=(b 1) rel2=(b 2)
     clause=1 restriction=0 action=PROPOSE
PGOJ LEGAL_MATCH oj=3 type=FULL orientation=NORMAL
PGOJ PATH_RESULT canonical=(b 1 2 3)
     rel1=(b 1) rel2=(b 2) pathlist_before=0 pathlist_after=1
PGOJ DP_LEVEL_END level=2 result_count=1

PGOJ DP_LEVEL_BEGIN level=2 initial_count=2
PGOJ DP_INITIAL slot=1 relids=(b 1 2 3)
PGOJ DP_INITIAL slot=2 relids=(b 4)
PGOJ PAIR_GATE level=2 rel1=(b 1 2 3) rel2=(b 4)
     clause=1 restriction=0 action=PROPOSE
PGOJ LEGAL_MATCH oj=5 type=FULL orientation=NORMAL
PGOJ PATH_RESULT canonical=(b 1 2 3 4 5)
     rel1=(b 1 2 3) rel2=(b 4) pathlist_before=0 pathlist_after=1
PGOJ DP_LEVEL_END level=2 result_count=1
```

There is no global level-2 `{B,C}` `PAIR_GATE`, no `{B,C}` proposal, and no
global level 3. Thus the missing tree is not rejected by `join_is_legal()`; it
is removed earlier by the nested joinlist structure:

```text
PostgreSQL space: (A FULL B) FULL C
missing tree:     A FULL (B FULL C)
```

Here “no FULL reordering” means no **reassociation of FULL-join nodes**.
PostgreSQL can still choose hash versus merge implementation and can reverse
the physical inputs of an individual commutative FULL join; neither operation
creates the missing `A FULL (B FULL C)` grouping.

For strict edge predicates such as these equalities, the two trees are
bag-equivalent.  For each occurrence of a `B` row, both produce its matching
`A` occurrence bag (or one null-padded `A`) times that `B` occurrence times
its matching `C` occurrence bag (or one null-padded `C`).  Both also preserve
every `A` or `C` occurrence with no matching `B`.  The SQL witness checks this
again with bidirectional `EXCEPT ALL`.

### Exact optimality calculation

For the written grouping:

```text
|A FULL B|             = N^2 + N
|(A FULL B) FULL C|    = N^2 + N
C(P_pg)                = 2N^2 + 2N
```

For the missing grouping:

```text
|B FULL C|             = N
|A FULL (B FULL C)|    = N^2 + N
C(P_alt)               = N^2 + 2N
```

Therefore:

```text
C(P_pg) - C(P_alt) = N^2 > 0
```

The connected predicate graph `A-B-C` has only these two
cross-product-free binary groupings, so the missing tree is the unique optimum
under cumulative intermediate-output work.

The supplied SQL was also executed on the same PostgreSQL 16.2 engine at
`N=100`:

```text
bidirectional EXCEPT ALL multiset_delta = 0

written inner FULL output = 10,100
written root output       = 10,100
written C(T)              = 20,200

alternative inner FULL output = 100
alternative root output       = 10,100
alternative C(T)              = 10,200
```

The final verification run reported `1.248 ms` for the written tree and
`0.516 ms` for the forced alternative. Those two timings are illustrative, not a
benchmark; the exact cardinalities and exhaustive two-tree comparison are the
optimality proof.

At `N=1000`, the release OuterYan trace agrees with the exact calculation:

```text
baseline_cost=2002000
candidate_join_cost=1002000
baseline_join_input_rows=1004001
candidate_join_input_rows=4001
semijoin_raw_cost=0
selected_plan=OUTERYAN
gate_result=PASS
```

This separates two claims cleanly:

1. The PostgreSQL trace proves the cheaper association is absent from its
   logical search space.
2. Exact cardinalities, same-engine execution, and the OuterYan trace prove
   that the absent association is the better plan for this witness.  This is
   not a cardinality-estimation explanation.

## Additional barrier witness: `(A FULL B) LEFT C`

```sql
SELECT a.k, b.k, c.k
FROM (a FULL OUTER JOIN b ON a.k = b.k)
LEFT OUTER JOIN c ON a.k = c.k;
```

For this query the trace bitmap IDs are:

```text
1=A, 2=B, 3=O1(the lower FULL), 4=C, 5=O2(the upper LEFT)
```

The decisive construction trace is:

```text
PGOJ FULL_BARRIER oj=3 left=(b 1) right=(b 2)
     action=MAKE_NESTED_SUBPROBLEM

PGOJ SJI_FULL_EXACT oj=3 rule=MIN_EQUALS_SYN
     minL=(b 1) minR=(b 2)

PGOJ MIN_INIT oj=5 clause=(b 1 3 4) strict=(b 1 4)
     lhs_strict=1 minL=(b 1 3) minR=(b 4)

PGOJ MIN_SCAN current_oj=5 lower_oj=3 lower_type=FULL
PGOJ MIN_RULE current_oj=5 rule=LOWER_FULL_BARRIER side=L
     lower_oj=3 result=(b 1 2 3)

PGOJ SJI_FINAL oj=5 type=LEFT
     minL=(b 1 2 3) minR=(b 4)
```

`clause=(b 1 3 4)` is not a typo.  Above `O1`, the `a.k` Var carries
`varnullingrels={3}`; `pull_varnos()` includes such outer-join relids.  Thus
the initial left minimum is `{A,O1}`.  Scanning lower FULL `S1` expands it to
the whole lower join, `{A,B,O1}`.

Here is the decisive, abridged normal proposal stream:

```text
PGOJ DP_LEVEL_BEGIN level=2 initial_count=2
PGOJ DP_INITIAL slot=1 relids=(b 1)
PGOJ DP_INITIAL slot=2 relids=(b 2)
PGOJ PAIR_PROPOSE rel1=(b 1) rel2=(b 2) union=(b 1 2)
PGOJ LEGAL_MATCH oj=3 type=FULL
PGOJ ADD_OJ_END action=ADD_NONLEFT_OWN_OJ oj=3 result=(b 1 2 3)

PGOJ DP_LEVEL_BEGIN level=2 initial_count=2
PGOJ DP_INITIAL slot=1 relids=(b 1 2 3)
PGOJ DP_INITIAL slot=2 relids=(b 4)
PGOJ PAIR_PROPOSE rel1=(b 1 2 3) rel2=(b 4)
     union=(b 1 2 3 4)
PGOJ LEGAL_MATCH oj=5 type=LEFT
PGOJ ADD_OJ_END action=COMPLETE result=(b 1 2 3 4 5)
```

There is no three-item DP problem and no `{A,C}` or `{B,C}` proposal.  This is
stronger and more accurate evidence than inventing a `LEGAL_REJECT` record.
If `{A,C}` were passed to `join_is_legal()` in a separately forced audit, it
would conflict with `S2`: it overlaps `S2.minR={C}`, does not contain all of
`S2.minL={A,B,O1}`, and also overlaps that minimum through `A`.  The
`RHS_CONFLICT` branch would therefore reject it.  That counterfactual check is
not part of normal PostgreSQL enumeration.

As an instrumentation control, the flattened query

```sql
SELECT * FROM (a LEFT JOIN b ON a.k=b.k) CROSS JOIN c;
```

really proposes `{B,C}` and produces:

```text
PGOJ PAIR_PROPOSE rel1=(b 4) rel2=(b 2) union=(b 2 4)
PGOJ LEGAL_STATE candidate=(b 2 4) oj=3 action=SET_MUST_BE_LEFT
PGOJ LEGAL_REJECT candidate=(b 2 4) oj=0
     reason=MUST_BE_STRICT_LEFT match=NONE
PGOJ PAIR_RESULT union=(b 2 4) accepted=0
```

This verifies that the logger prints a reject when `join_is_legal()` is
actually reached.

## Complete `minL` / `minR` construction rules

`make_outerjoininfo()` is called bottom-up.  Previously appended entries are
therefore precisely the syntactically lower special joins.

1. For current FULL, set `minL=synL`, `minR=synR`, set no commute relation,
   and return without scanning older entries.
2. Otherwise initialize

   ```text
   clause_relids = pull_varnos(clause)
   strict_relids = find_nonnullable_rels(clause)
   lhs_strict    = overlaps(strict_relids, synL)
   minL          = clause_relids intersect synL
   minR          = (clause_relids union inner_join_rels) intersect synR
   ```

3. Scan each older `SpecialJoinInfo S` in append (bottom-up) order.
   If `S` is FULL and overlaps a current syntactic side, add
   `S.synL union S.synR union {S.ojrelid}` to that side's minimum, then
   continue to the next `S`.
4. For an older non-FULL join whose nullable `S.synR` overlaps the current
   LHS, preserve order by adding all of `S` to `minL` when the current clause
   uses `S.synR` and either an unsafe PHV exists, the current join is
   SEMI/ANTI, or the clause is not strict on `S.minR`.  Otherwise, two LEFT
   joins can use identity 3 when strict on `S.minR` and the current clause
   does not use `S.synL`: delete `S.ojrelid` from `minL` and tentatively add it
   to `commute_below_l`.
5. For an older non-FULL join whose nullable `S.synR` overlaps the current
   RHS, preserve order by adding all of `S` to `minR` if the clause uses
   `S.synR`, does not use `S.minL`, has an unsafe PHV, either join is
   SEMI/ANTI, or `S.lhs_strict` is false.  Otherwise two LEFT joins with
   `S.lhs_strict` can use identity 3: delete `S.ojrelid` from `minR` and
   tentatively add it to `commute_below_r`.
6. Add every RHS-syntactic PlaceHolderVar's `ph_eval_at` set to `minR`.
   Replace an empty minimum with its full syntactic side.
7. Remove from tentative commute sets any OJ IDs subsequently reintroduced
   into a minimum.  Store the surviving `commute_below_*` sets and backpatch
   reciprocal `commute_above_*` sets in the older entries.

Only the identity-3 case backpatches an older `SpecialJoinInfo`; ordinary
minimum-set expansion changes the current entry only.

## Other missing-plan witnesses

Use exact intermediate-output work

```text
C(T) = sum of |join output| over the binary joins in T.
```

The current OuterYan DP uses this cumulative shape, plus separately reported
semi-join work.  The following additional witnesses use only key `1` rows.

| Witness | Cardinalities | PostgreSQL-only grouping and join cost | OuterYan grouping and join cost |
|---|---:|---:|---:|
| Q1: `(A FULL B) LEFT C` | `|A|=1, |B|=N, |C|=1` | `(A FULL B) LEFT C`: `2N` | `B FULL (A LEFT C)`: `N+1` |
| Q3: `(A RIGHT B) FULL C` | `|A|=|B|=N, |C|=1` | `(A RIGHT B) FULL C`: `2N^2` | `A RIGHT (B FULL C)`: `N^2+N` |
| Q4: `((A FULL B) FULL C) FULL D` | `|A|=|B|=100, |C|=|D|=1` | written left-deep tree: `30,000` | `A FULL (B FULL (C FULL D))`: `10,101` |

Release-build OuterYan traces report:

| Witness and scale | PG/DuckDB baseline | OuterYan real joins | SJ work | OuterYan total | Selected |
|---|---:|---:|---:|---:|---|
| Q1, `N=1000` | `2,000` | `1,001` | `5` | `1,006` | OuterYan |
| all-FULL witness above, `N=1000` | `2,002,000` | `1,002,000` | `0` | `1,002,000` | OuterYan |
| Q3, `N=1000` | `2,000,000` | `1,001,000` | `5,000` | `1,006,000` | OuterYan |
| Q4, `N=100,100,1,1` | `30,000` | `10,101` | `0` | `10,101` | OuterYan |

The all-FULL PostgreSQL trace contains two `FULL_BARRIER` events and only the
two scopes `[{A},{B}]` and `[{A,B,O1},{C}]`.  Q3 has an upper FULL barrier;
PostgreSQL first completes its normalized lower `B LEFT A`, then joins `C`.
Q4 emits three nested FULL barriers.  Its five connected binary groupings have
costs `30,000`, `20,100`, `20,001`, `10,200`, and `10,101`, respectively, so
the OuterYan right-deep tree is the unique minimum among all five.

For each three-node path there are only two connected, cross-product-free
binary groupings.  The OuterYan grouping is the unique minimum under `C(T)`
for the stated scales (and remains cheaper after Q1/Q3 semi-join work for
`N>6`).  All cardinalities used here are exact, so these are plan-space
witnesses, not cardinality-estimation anecdotes.

The transformations are bag-semantics valid for the strict, edge-local
equality predicates used here.  They were also checked bidirectionally with
`EXCEPT ALL` on duplicate, NULL-key, and unmatched-key data.

This does not by itself claim cross-engine wall-clock optimality.  It proves
that a strictly cheaper logical tree under OuterYan's stated cost objective is
present in OuterYan's enumeration and absent from PostgreSQL's logical
association space.

## Reproduction

From the repository root, use **Bash** to build and install the instrumented
source, restart the managed postmaster with `PG_OJ_TRACE=1`, and run the
witness file. The variable must be present in the postmaster environment;
setting it only in the `psql` client is too late.

```sh
set -euo pipefail
source auto_test/configs.sh

make -C postgres/postgresql-16.2 -j8
make -C postgres/postgresql-16.2 install

if "$PGPLAN_INSTALL_DIR/bin/pg_ctl" -D "$PGPLAN_DATA_DIR" status \
    >/dev/null 2>&1; then
  "$PGPLAN_INSTALL_DIR/bin/pg_ctl" \
    -D "$PGPLAN_DATA_DIR" -m fast -w stop
fi

PG_OJ_TRACE=1 "$PGPLAN_INSTALL_DIR/bin/pg_ctl" \
  -D "$PGPLAN_DATA_DIR" \
  -l /tmp/duckyan_pg_oj_server.log \
  -o "-h $PGPLAN_HOST -p $PGPLAN_PORT" -w start

PGPASSWORD="$PGPLAN_PASSWORD" "$PSQL_BIN" -X \
  --set=ON_ERROR_STOP=1 \
  --dbname="$PG_DSN" \
  --file=auto_test/pg_oj_trace/witnesses.sql \
  > /tmp/pg_oj_trace_full.log 2>&1

# Restore the managed server without research tracing.
"$PGPLAN_INSTALL_DIR/bin/pg_ctl" \
  -D "$PGPLAN_DATA_DIR" -m fast -w stop
"$PGPLAN_INSTALL_DIR/bin/pg_ctl" \
  -D "$PGPLAN_DATA_DIR" \
  -l "$PGPLAN_LOG_FILE" \
  -o "-h $PGPLAN_HOST -p $PGPLAN_PORT" -w start
```

`configs.sh` supplies the managed database, user, password, and TCP endpoint;
the command does not print the password. The observed validation used the
pinned PostgreSQL 16.2 server, `geqo=off`, collapse limits `16`, and no parallel
gather. On 2026-08-31, this exact file completed with exit status `0` and 788
lines of output. The identity-3 and all-FULL records quoted above come from
that run.

The local research instrumentation is in the pinned PostgreSQL source at:

- `postgres/postgresql-16.2/src/backend/optimizer/plan/initsplan.c`
- `postgres/postgresql-16.2/src/backend/optimizer/path/joinrels.c`

The release OuterYan evidence is in:

- `/tmp/oy_witness_q1_gated_20260830.log`
- `/tmp/oy_best_full_exact_outer_n1_20260830.log`
- `/tmp/oy_best_full_exact_outer_n1000_insert_20260830.log`
- `/tmp/oy_witness_q3_gated_20260830.log`
