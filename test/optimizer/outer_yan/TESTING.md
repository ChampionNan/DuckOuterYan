# OuterYan Optimizer — Test Suite Reference

Test coverage for the **OuterYan** join-reordering and semi-join insertion
optimizer sub-phases introduced in `src/optimizer/outer_yan/`.

---

## Directory layout

```
test/optimizer/outer_yan/          # C++ unit / white-box tests (Catch2)
    applicability_test.cpp
    hash_filter_test.cpp
    key_bitmap_test.cpp
    semi_join_filter_test.cpp
    passes_integration_test.cpp
    CMakeLists.txt
    TESTING.md                     # this file

test/sql/optimizer/outer_yan/      # SQL end-to-end tests (sqllogictest)
    acyclic_query.test
    bitmap_budget.test
    fallback.test
    feature_flag.test
    outer_join_aggregate.test
    outer_join_chain.test
    semijoin_passes.test
    tpch_outer.test
    tpcds_outer.test
    tpch_outer.test_slow           # slow tier — sf=0.01 + reference CSVs
    tpcds_outer.test_slow          # slow tier — sf=0.1 full TPC-DS suite

    # 3-way filter comparison: BITMAP vs HASH vs DuckDB-own baseline
    tpch_semi_join_comparison.test          # sf=0.01 — 5 TPC-H queries
    tpcds_semi_join_comparison.test         # sf=0  — 4 TPC-DS queries (smoke)
    tpcds_semi_join_comparison.test_slow    # sf=0.1 — same 4 queries with data
```

---

## How to run

### Build (debug + unit tests)

```bash
GEN=ninja make debug
```

### C++ unit tests only

The `unittest` binary selects C++ tests by Catch2 tag. Each `.cpp` file has its
own second-level tag; the tag is the second string argument to every `TEST_CASE`.

Run the full OuterYan C++ suite:

```bash
build/debug/test/unittest "[outer_yan]"
```

Run one file at a time:

```bash
build/debug/test/unittest "[outer_yan][applicability]"    # applicability_test.cpp
build/debug/test/unittest "[outer_yan][hash_filter]"      # hash_filter_test.cpp
build/debug/test/unittest "[outer_yan][key_bitmap]"       # key_bitmap_test.cpp
build/debug/test/unittest "[outer_yan][semi_join_filter]" # semi_join_filter_test.cpp
build/debug/test/unittest "[outer_yan][passes]"           # passes_integration_test.cpp (white-box + equivalence)
build/debug/test/unittest "[outer_yan][equivalence]"      # passes_integration_test.cpp (off-vs-on only)
```

Run one specific test case (exact `TEST_CASE` name string):

```bash
build/debug/test/unittest "outer_yan applicability: rejects theta predicate"
```

List all case names in a sub-suite:

```bash
build/debug/test/unittest --list-tests "[outer_yan][applicability]"
```

### SQL end-to-end tests

`sqllogictest` is **not** a separate binary — all SQL tests run through `unittest`.
Pass the file path directly as the selector.

Run all SQL + C++ tests in the group:

```bash
build/debug/test/unittest "[outer_yan]"
```

Run one SQL file at a time:

```bash
build/debug/test/unittest test/sql/optimizer/outer_yan/acyclic_query.test
build/debug/test/unittest test/sql/optimizer/outer_yan/bitmap_budget.test
build/debug/test/unittest test/sql/optimizer/outer_yan/fallback.test
build/debug/test/unittest test/sql/optimizer/outer_yan/feature_flag.test
build/debug/test/unittest test/sql/optimizer/outer_yan/outer_join_aggregate.test
build/debug/test/unittest test/sql/optimizer/outer_yan/outer_join_chain.test
build/debug/test/unittest test/sql/optimizer/outer_yan/semijoin_passes.test
build/debug/test/unittest test/sql/optimizer/outer_yan/tpch_outer.test
build/debug/test/unittest test/sql/optimizer/outer_yan/tpcds_outer.test
build/debug/test/unittest test/sql/optimizer/outer_yan/tpch_semi_join_comparison.test
build/debug/test/unittest test/sql/optimizer/outer_yan/tpcds_semi_join_comparison.test
```

Slow tests (require TPC-H / TPC-DS extensions):

```bash
build/debug/test/unittest test/sql/optimizer/outer_yan/tpch_outer.test_slow
build/debug/test/unittest test/sql/optimizer/outer_yan/tpcds_outer.test_slow
build/debug/test/unittest test/sql/optimizer/outer_yan/tpcds_semi_join_comparison.test_slow
```

### With sanitizers

```bash
BUILD_UNITTEST=1 ENABLE_SANITIZER=1 GEN=ninja make debug
build/debug/test/unittest "[outer_yan]"
```

### Useful diagnostics during development

```sql
PRAGMA enable_verification;
PRAGMA verify_parallelism;
PRAGMA explain_output='optimized_only';

-- Safe disable options (dp / post alone break plan ownership; do not use):
SET disabled_optimizers TO 'outer_yan_pre';                        -- short-circuits whole pipeline
SET disabled_optimizers TO 'outer_yan_pre,outer_yan_dp,outer_yan_post';  -- explicit all-off
SET disabled_optimizers TO 'aggregate_pushdown_outer';             -- independent; always safe

-- Bitmap budget control:
SET VARIABLE outer_yan_bitmap_max_bytes = 0;          -- force HashFilter
SET VARIABLE outer_yan_bitmap_max_bytes = 34359738368; -- restore server default (32 GiB)
```

---

## C++ unit tests

### `applicability_test.cpp` — Applicability gate

Tests `OuterYanApplicability::Check` (white-box) and
`OuterYanTree::CheckApplicability` (integration path).

| Test case | What it verifies |
|---|---|
| rejects pure-INNER 2-relation join | Pure-INNER with no outer → `applicable = false` |
| rejects pure-INNER 3-relation chain | Three-way inner chain → `applicable = false` |
| accepts 3-relation LEFT-LEFT chain | Canonical accepted shape → `applicable = true`, 3 relations, ≥2 edges |
| accepts mix of INNER + LEFT | One outer is sufficient → `applicable = true` |
| accepts LEFT/RIGHT mix | Mixed outer direction → `applicable = true` |
| accepts FULL OUTER in chain | `FULL OUTER` counts as outer → `applicable = true` |
| rejects theta predicate | `<` instead of `=` on join key → `applicable = false` |
| rejects expression on join key | `a.id + 1 = b.id` → `applicable = false` |
| rejects IS NOT DISTINCT FROM (NULL-tolerant) | NULL-tolerant join → `applicable = false` |
| rejects cross product | No join condition → `applicable = false` |
| rejects set op above join | `UNION ALL` above skeleton → `applicable = false` |
| rejects window operator above join | `ROW_NUMBER() OVER` above skeleton → `applicable = false` |
| rejects cyclic 3-relation graph | Triangle (a–b, a–c, b–c) → `applicable = false` |
| accepts root aggregation (COUNT_STAR) | Aggregate at root → `applicable = true`, `has_root_aggregate = true` |
| accepts GROUP BY at root | Group-by at root → `applicable = true`, `has_root_aggregate = true` |
| relation table-index mapping is populated | 3 distinct `RelationId`s in [0, 3) after accept |
| edges hold valid LogicalComparisonJoin pointers | `edge.join != nullptr`, `edge.left != edge.right` |
| rejection populates reason string | `result.reason` non-empty on any rejection |
| OuterYanTree::CheckApplicability accepts on outer chain | Integration path mirrors white-box for accepted shape |
| OuterYanTree::CheckApplicability rejects pure-INNER | Integration path mirrors white-box for rejected shape |

### `hash_filter_test.cpp` — HashFilter + HashFilterUseKernel

Tests the open-addressed exact set-membership structure used when
`KeyBitmap` is not applicable (VARCHAR, DECIMAL, composite keys, or range
exceeds the byte budget).

| Test case | What it verifies |
|---|---|
| fresh filter is empty | `Count() == 0`, `IsEmpty()`, `!IsFinalized()`, `Capacity() == 64` |
| build + Contains round-trip on single-column INTEGER | Build 3 rows, probe hit/miss |
| empty filter Contains is false for any key | Zero-row filter returns false for any probe |
| duplicate inserts collapse to one key (set semantics) | 5 inserts with 2 distinct keys → `Count() == 2` |
| NULL keys skipped at build time | NULLs in build chunk not inserted, non-NULLs indexed |
| NULL probe key never matches | NULL in probe key → miss regardless of build side |
| VARCHAR keys | String build + probe round-trip |
| composite (INTEGER + VARCHAR) keys | Two-column compound key build + probe |
| composite key with one NULL column skipped | Row with any NULL column skipped entirely |
| Build after Finalize throws | `InternalException` on second Build after Finalize |
| Merge after Finalize throws | `InternalException` on Merge into finalized filter |
| Build with empty build_col_ids throws | `InternalException` on zero-width key |
| load-factor stress — many resizes preserve all keys | 10 000 keys, all survive; load ≤ 3/4 |
| Merge union of two disjoint thread-local filters | `dst.Count() == 6`; `src` is reset |
| Merge with overlapping keys = union cardinality | Shared keys deduplicated, union preserved |
| Merge with empty src is no-op | `dst.Count()` unchanged |
| Merge into empty dst | Keys from `src` appear in `dst`; `src` reset |
| MurmurHash64A is deterministic and order-sensitive | Same data → same digest; different seed → different |
| HashKey composes per-column hashes | Order-dependent: `(1, "a") != ("a", 1)` |
| filter narrows selection vector | Probe {2,1,5,4,3} against build {1,3,5} → sel[0..2] = {1,2,4} |
| empty filter survives no rows | Zero-row build → `approved == 0` |
| NULL probe keys do not survive | NULLs in probe chunk excluded from `sel` |
| empty probe_col_ids throws | `InternalException` from `HashFilterUseKernel::filter` |
| composite-key probe filtering | Two-column probe narrows correctly |
| **MURMUR_HASH2 kind — Build+Contains end-to-end** | Explicit `HashKind::MURMUR_HASH2` constructor; hash path exercised |
| **IsInline64Eligible — integer types eligible, others not** | INT8/16/32/64 + UINT8/16/32/64 → true; VARCHAR/FLOAT/composite → false |
| **IsInline64() + InlineKeyType() set after integer Build** | `IsInline64() == true`, `InlineKeyType() == PhysicalType::INT32` after INTEGER build |
| **KeyArity() is 0 before Build and matches col count after** | Single-col → 1, two-col composite → 2 |

> **Bold** entries were added to cover previously untested API surface.

**Parallel-build helpers** (`ReserveInline`, `BuildChunkInline64<PARALLEL>`)
are not exercised directly; they are driven by `PhysicalSJBuild`'s event
chain and covered end-to-end by the SQL integration tests.

### `key_bitmap_test.cpp` — KeyBitmap

Tests the dense bit-per-value probe structure for integer / date join keys.

| Test case | What it verifies |
|---|---|
| builds and probes contiguous integer range | `[1,7]` with gaps; `PopCount == 5`; hit/miss correct |
| out-of-range probe never matches | Probes below `MinKey` and above `MaxKey` return false; INT64 extremes safe |
| empty build emits zero-popcount bitmap | Empty CDC → `PopCount() == 0`, `IsEmpty()`, probe false |
| all-NULL build behaves as empty | All-NULL build column → `IsEmpty()` |
| NULL keys skipped, non-NULL keys indexed | Mixed NULL/non-NULL → only non-NULL bits set |
| single-row build sets exactly one bit | `MinKey == MaxKey == 42`, `PopCount == 1` |
| word-boundary keys (63, 64, 65, 128 …) | Keys straddling 64-bit word boundaries indexed correctly |
| negative integer keys | `[-3, 3]` range, negatives probed correctly |
| BIGINT type dispatch | Large BIGINT keys (1 000 000 000+) indexed |
| UINTEGER type dispatch | Unsigned 32-bit keys indexed |
| DATE type dispatch | `Date::days` values indexed |
| VARCHAR rejected — TryBuild returns nullptr | Non-integer key type → nullptr |
| DECIMAL rejected — TryBuild returns nullptr | DECIMAL → nullptr |
| UBIGINT rejected (overflow-prone) | UBIGINT → nullptr (int64_t range overflow risk) |
| composite key rejected (v1 single-column only) | `build_col_ids.size() > 1` → nullptr |
| byte_budget = 0 always returns nullptr | Zero budget → nullptr regardless of key type |
| budget boundary — fits exactly vs overflows by 1 | `[0,79]` needs 10 bytes: fit@10 ≠ nullptr, fit@9 == nullptr |
| ProbeBatch narrows selection vector | `{2,1,5,4,3}` against build `{1,3,5}` → sel = {1,2,4} |
| ProbeBatch with all out-of-range keys filters everything | Keys below MinKey → `approved == 0` |
| ProbeBatch on empty bitmap survives no rows | Empty bitmap → `approved == 0` |
| ProbeBatch with NULL probe keys skips them | NULLs excluded from `sel` |
| ProbeBatch with empty probe_col_ids throws | `InternalException` on empty ids |
| empty / mismatched build_col_ids → nullptr | Empty or size-mismatch returns nullptr |
| large range across many words | 1024 keys [0..1023] = 128 bytes; all indexed |
| sparse range still indexed if budget allows | `{0, 999}` at budget 256 → OK; at budget 100 → nullptr |
| duplicate keys in build set produce a single bit | Four inserts of key=1 → `PopCount == 2` (1 and 2) |
| SizeBytes matches bit_count_/8 | `SizeBytes() == BitCount() / 8`, `BitCount() % 64 == 0` |
| **CheckEligibility — integer types eligible, others not** | INTEGER/BIGINT/UINTEGER/DATE → eligible; VARCHAR/FLOAT/DECIMAL/composite → not |

> **Bold** entry was added to cover the `CheckEligibility` static method
> used by `PhysicalSJBuild::Finalize` to gate the parallel bitmap event chain.

**Parallel-build helpers** (`ScanMinMaxRange`, `ReduceMinMax`, `Allocate`,
`FillBitsRange<PARALLEL>`, `FinalizePopCount`) are not exercised directly;
they delegate through `TryBuild`'s sequential path and are covered
end-to-end by the integration suite.

### `semi_join_filter_test.cpp` — SemiJoinFilter

Tests the tagged-union carrier (`UNDECIDED → BITMAP | HASH`) shared between
`LogicalSJBuild` and `LogicalSJProbe`.

| Test case | What it verifies |
|---|---|
| fresh instance is UNDECIDED | `kind() == UNDECIDED`, `!finalized()`, `IsEmpty()` |
| force_hash hint defaults off and is settable | `ForceHash()` sets the flag; does not change `kind` or finalize |
| hash() returns the finalized filter by reference | `&f.hash() == hf.get()`, `hash_shared().get() == hf.get()` |
| FinalizeAsHash transitions to HASH and IsEmpty delegates | `kind() == HASH`, `finalized()`, `IsEmpty()` mirrors `HashFilter::IsEmpty()` |
| FinalizeAsBitmap transitions to BITMAP and IsEmpty delegates | `kind() == BITMAP`, `finalized()`, `IsEmpty()` mirrors `KeyBitmap::IsEmpty()` |
| double-finalize throws | Second `FinalizeAsHash` or cross-kind finalize → `InternalException` |
| empty hash filter reports IsEmpty | `HashFilter::IsEmpty()` propagated |
| zero-cardinality bitmap reports IsEmpty | Empty `KeyBitmap` propagated |

### `passes_integration_test.cpp` — pipeline white-box + result equivalence

Two complementary groups, both driven through the public construction path
`optimizer.cpp` uses.

**White-box** (`[passes]` — `BuildIRFor` builds OT/OJT with the pipeline
disabled, then inspects the IR):

| Test case | What it verifies |
|---|---|
| OT::IsValid holds on 3-relation LEFT chain | `OT.IsValid()` returns true, `reason` empty |
| OT shape — 3-relation chain has 2 JOINs + 3 RELATIONs | `CountJoinNodes == 2`, `CountRelationNodes == 3` |
| OT shape — 4-relation chain has 3 JOINs + 4 RELATIONs | Scales to 4 |
| OT relation_id uniqueness — each base relation distinct | `ot_relations_by_id[i].relation_id == i` for all i |
| ot_joins_by_order is sorted ascending by `order` | Monotone order field |
| null-rejecting WHERE simplifies LEFT to INNER | `WHERE b.bx > 0` → at least one edge flips to INNER in OJT |
| no simplification when WHERE preserves NULLs | `WHERE b.bx IS NULL OR b.bx > 0` → outer kind retained |
| semi-join pair recording populates both phases | EXPLAIN shows `SJ_BUILD` and `SJ_PROBE` for accepted query |
| OJT has the same relation count as OT | `ojt_nodes == 3` for 3-relation query |
| OJT root has subtree containing all relations | All 4 relation IDs reachable from OJT root |
| applicability rejection short-circuits — no OT built | `HasOT() == false`, `HasOJT() == false` after rejection |

**Result equivalence** (`[equivalence]` — via `AssertOuterYanPreservesResults`):
each query runs with `disabled_optimizers='outer_yan'` (ordinary DuckDB /
JOIN_ORDER) and again with `''` (full `OuterYanPre → DP → Post`); the two
**sorted row multisets** (`CollectSortedRows`, so no `ORDER BY`) must match.
Every query carries an outer join so the gate fires; join conditions are binary
equi-joins; residual `WHERE` filters reference a single relation on the
preserved side. NULL-rich `SeedNullable` data (NULL keys that never match, NULL
payloads, duplicate keys) stresses NULL-padding and multiset preservation.

| Test case | What it verifies |
|---|---|
| 2-relation LEFT join | LEFT_OUTER NULL-padding; 2×2 many-to-many preserved |
| 2-relation RIGHT join | RIGHT-outer through the production flip path |
| 2-relation FULL OUTER join | Exclusive and NULL keys surface from both sides |
| 3-relation LEFT chain | Three-way LEFT chain end-to-end |
| RIGHT-flip mirror (`b RIGHT JOIN a`) + LEFT tail | OJT parent-orientation may flip RIGHT↔LEFT; NULLs preserved |
| FULL OUTER head + LEFT tail | `FULL OUTER` followed by `LEFT` survives the pipeline |
| mixed INNER/LEFT/FULL chain | Three join kinds in one skeleton, all keyed on `na.k` |
| 4-relation LEFT chain | Deeper chain through DP enumeration |
| LEFT join with preserved-side residual filter | `na.v > 15` push is result-preserving |
| compound equi-join condition on a LEFT edge | Two binary conditions on one edge, both swappable |
| bushy tree with an outer join | Parenthesised `((na,nb),(nc,nd))` with a LEFT arm |
| projection prunes to a single column over outer join | Output schema reproduced from the null-supplying side |
| 5-relation LEFT chain | DP enumeration scales to 5 relations |
| 6-relation LEFT star | Star-shaped graph with 6 relations |
| residual filter via projection (UNSUPPORTED — hidden `[.]`) | The one isolated check: `LogicalPlanToOT` throws `NotImplementedException` on a projection-introduced `table_index` (the gate hides this in production, so result-equivalence can't surface it) |

---

## SQL end-to-end tests

All SQL tests use `PRAGMA enable_verification` and `PRAGMA verify_parallelism`.

### `acyclic_query.test` — Applicability gate + SJ_PROBE presence

Verifies that `EXPLAIN` shows `SJ_PROBE` for accepted shapes and `<!REGEX>`
confirms absence for rejected shapes. Also checks result-equivalence for
accepted queries with OuterYan enabled vs disabled.

**Accepted shapes** (produce `SJ_PROBE` in `EXPLAIN`):
- 3-relation LEFT-LEFT chain
- 3-relation LEFT-RIGHT mix
- FULL OUTER somewhere in the chain
- 4-relation chain
- INNER + LEFT mix
- Star shape (3 dim tables off one fact)

**Rejected shapes** (no `SJ_PROBE`):
- Pure-INNER 2-relation and 3-relation chains
- Theta predicate (`<`)
- Expression on join key (`a.id + 1 = b.id`)
- `IS NOT DISTINCT FROM` (NULL-tolerant equi)
- `EXISTS` / `NOT EXISTS` (SEMI / ANTI join)
- `UNION ALL` above join skeleton
- Window function above join skeleton
- Cyclic join graph
- Cross product (no condition on one pair)
- Correlated subquery in `WHERE`

### `bitmap_budget.test` — Bitmap vs HashFilter path selection

| Block | What it tests |
|---|---|
| Default budget (32 GiB) | Small INTEGER keys → BITMAP path; result correct |
| Budget = 0 | Forces HashFilter on all filters; result identical to BITMAP path |
| Tiny budget (16 bytes) | Range [1, 999] exceeds 16 bytes → HashFilter |
| VARCHAR keys | Type-ineligible → HashFilter; result correct at budget 0 and default |
| Mixed schema (int + varchar filters) | Each filter decided independently |
| Large build side (4 999 rows) | HashFilter with resizing at load-factor 3/4 |
| Large build + budget 256 | Range [1, 4999] = ~625 bytes → HashFilter forced |

### `fallback.test` — Rejected shapes fall back correctly

Each block runs the same query twice: OuterYan enabled, then disabled.
Identical result sets prove fallback is semantics-preserving.

Covers: pure-INNER 2-relation, pure-INNER 3-relation,
theta predicate, expression on key, `IS NOT DISTINCT FROM`, `EXISTS`,
`NOT EXISTS`, `UNION ALL`, window function, cyclic join graph, cross product,
correlated subquery.

### `feature_flag.test` — Safe pass disable combinations

`outer_yan_pre` is the only individually safe toggle: disabling it keeps
`outer_yan_active = false`, so DP / Post / AggPushdown are all skipped by
the `if (outer_yan_active)` guard in `optimizer.cpp`. Disabling `dp` or
`post` alone corrupts plan ownership because Pre has already moved the plan
into the tree.

| Scenario | Expected behavior |
|---|---|
| All passes enabled | `SJ_PROBE` in EXPLAIN |
| `outer_yan_pre` disabled | `outer_yan_active` stays false; entire pipeline short-circuited; no `SJ_PROBE` |
| All three disabled | Full revert to baseline JoinOrderOptimizer |
| Re-enable after disable | `SJ_PROBE` reappears; toggle is reversible |
| Pure-INNER query under `outer_yan_pre` disabled | Same baseline; no interference |
| `aggregate_pushdown_outer` disabled alone | Pre/DP/Post still fire; pushdown skipped; results identical |

### `outer_join_chain.test` — Outer-join chain semantics (15 variants)

Every variant runs the query with OuterYan enabled and disabled; results must match exactly including NULL counts.

| Variant | Shape |
|---|---|
| 1 | LEFT/LEFT chain |
| 2 | RIGHT/RIGHT chain (covers `RIGHT_OUTER → LEFT_OUTER` flip) |
| 3 | Mixed LEFT/RIGHT (exercises Resimplification) |
| 4 | FULL OUTER at the head |
| 5 | FULL OUTER at the tail |
| 6 | 4-relation chain |
| 7 | 5-relation star (fact + 4 dims) |
| 8 | 5-relation chain (a → b → c → d → e) |
| 9 | Residual filter on single relation |
| 10 | Residual filter spanning two relations |
| 11 | Residual filter that null-rejects an outer column (simplification path) |
| 12 | Multiple equi-join conditions on the same edge (compound key) |
| 13 | Empty intermediate result (build side has no matching rows) |
| 14 | Build side has NULL keys (NULLs must never match) |
| 15 | Multi-row build side (many-to-one, fanout preserved) |

### `outer_join_aggregate.test` — Aggregate root over outer-join chains

Covers all `OuterYanAggregationType` variants with a result-equivalence
assertion (OuterYan enabled vs disabled). A pass-isolation section then
keeps pre/dp/post enabled and toggles only `aggregate_pushdown_outer`.

| Variant | Aggregate shape |
|---|---|
| 1 | `COUNT(*)` over LEFT-LEFT chain |
| 2 | `GROUP BY a.id` with `COUNT(b.bx)` |
| 3 | `SUM(c.cx)` with NULLs from outer joins |
| 4 | `MIN(b.bx)`, `MAX(c.cx)` |
| 5 | `SELECT DISTINCT` |
| 6 | `SUM` + `HAVING` |
| 7 | `COUNT(*)` on 4-way chain |
| 8 | Aggregation with mixed LEFT/RIGHT/FULL |
| 9 | `SUM(d.dx)` from deepest relation in 4-way chain |
| Pass-isolation | Each of COUNT_STAR, SUM, MIN/MAX, plain SUM, DISTINCT toggled under `aggregate_pushdown_outer` only |

### `semijoin_passes.test` — SJ_BUILD / SJ_PROBE presence per join type

Asserts that `EXPLAIN` shows `SJ_BUILD` and `SJ_PROBE` for each `OJTEdgeKind`:
LEFT-LEFT, INNER+LEFT, LEFT chain (varying connectivity), RIGHT-RIGHT, FULL OUTER + LEFT.
Correctness regression blocks follow for each shape.

### `tpch_semi_join_comparison.test` — BITMAP vs HASH vs DuckDB-own (TPC-H, sf=0.01)

Three-way parity test for the semi-join filter. Each query is materialised into
three temp tables (one per path) then compared via `EXCEPT ALL`.

| Command | Path elected |
|---|---|
| `SET VARIABLE outer_yan_bitmap_max_bytes = 34359738368` + `SET disabled_optimizers TO ''` | **BITMAP** (KeyBitmap for integer keys within range) |
| `SET VARIABLE outer_yan_bitmap_max_bytes = 0` + `SET disabled_optimizers TO ''` | **HASH** (HashFilter for every key type, budget = 0) |
| `SET disabled_optimizers TO 'outer_yan_pre,outer_yan_dp,outer_yan_post'` | **BASELINE** (DuckDB's own hash-join engine, no SJ operators) |

**EXPLAIN check**: BITMAP and HASH paths show `SJ_PROBE`; BASELINE does not.

| Query | Shape | Key angle |
|---|---|---|
| TH-Q1 | `customer LEFT JOIN orders LEFT JOIN lineitem` GROUP BY c_custkey | Primary 3-table LEFT chain; integer surrogate keys → bitmap |
| TH-Q2 | `nation LEFT JOIN supplier LEFT JOIN lineitem` GROUP BY n_name | Different dimension hierarchy; tests supply-chain chain |
| TH-Q3 | TH-Q1 + `WHERE c_mktsegment = 'BUILDING'` | Residual filter on preserved side; simplification pass |
| TH-Q4 | `customer LEFT JOIN orders LEFT JOIN lineitem LEFT JOIN supplier` GROUP BY c_custkey | 4-table chain — 3 SJ pairs |
| TH-Q5 | `partsupp LEFT JOIN part LEFT JOIN supplier` GROUP BY ps_partkey | Supply-cost dimension; min/max aggregate |

### `tpcds_semi_join_comparison.test` — BITMAP vs HASH vs DuckDB-own (TPC-DS, sf=0)

Same three-way pattern as the TPC-H file but at sf=0 (empty tables, smoke test).
All EXCEPT ALL queries return 0 by construction; primary value is no-crash
verification across all four TPC-DS query shapes.
`tpcds_semi_join_comparison.test_slow` repeats the same queries at sf=0.1 with
real data for a meaningful filter-path comparison.

| Query | Shape | Key angle |
|---|---|---|
| DS-Q1 | `date_dim LEFT JOIN store_sales LEFT JOIN item` GROUP BY d_year, i_brand_id | 3-table, date-dimension chain (q03 pattern) |
| DS-Q2 | `customer LEFT JOIN store_sales LEFT JOIN date_dim` GROUP BY c_customer_sk | 3-table star from customer |
| DS-Q3 | `catalog_sales LEFT JOIN customer LEFT JOIN date_dim LEFT JOIN item` GROUP BY cs_order_number | 4-table star from catalog_sales fact |
| DS-Q4 | `customer_demographics LEFT JOIN store_sales LEFT JOIN date_dim LEFT JOIN item LEFT JOIN promotion` GROUP BY i_item_id | 5-table star; WHERE clauses trigger simplification pass (q07 pattern) |

### `tpch_outer.test` — TPC-H smoke test (sf=0)

- **Q13** (`customer LEFT OUTER JOIN orders + GROUP BY`) — runs with and without OuterYan.
- **Derived Q3** (customer → orders → lineitem rewritten as LEFT OUTER) — same A/B.
- Both assert `statement ok` at sf=0 (empty tables; primary value is no crash).

### `tpcds_outer.test` — TPC-DS smoke test (sf=0)

- **Q05** (store/catalog/web channel rollup with LEFT OUTER inside a CTE) — UNION ALL above the skeleton causes applicability to reject; falls back to baseline. Both paths must succeed.
- Slow tier (`tpcds_outer.test_slow`) runs the full Q05 suite at sf=0.1.

---

## Known limitations (documented unsupported cases)

| Case | Status | Location |
|---|---|---|
| Residual filter referencing columns introduced by `LogicalProjection` above the join tree | `NotImplementedException` at `LogicalPlanToOT` | `passes_integration_test.cpp` — hidden test `[.]` |
| UBIGINT bitmap keys | Rejected by `TryBuild` (int64_t range overflow risk); falls back to HashFilter | `key_bitmap_test.cpp` |
| Composite bitmap keys | v1 supports single-column keys only; `TryBuild` returns nullptr | `key_bitmap_test.cpp` |
| Non-equi (theta) join predicates | Applicability rejects; baseline join order used | `acyclic_query.test`, `fallback.test` |
| Cyclic join graphs | Union-find cycle detection rejects; baseline used | `acyclic_query.test` |
| SIMD probe kernel | Scalar fallback is the only implementation; SIMD pending benchmark | — |
| Parallel HashFilter build (BOXED mode) | Only INLINE_64 supports parallel build; BOXED falls back to sequential | `hash_filter.hpp` comment |
