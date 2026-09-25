# OuterJoin benchmark design

This directory contains three versioned, provenance-backed workloads for
outer-join query optimization. **v1** remains the default, **v2** is the
selectivity expansion under `v2/`, and **v3** is the root-aggregation workload
under `v3/`.

The v1 layout contains one active benchmark plus three auditable component
views:

- `benchmark/` is the canonical active 224-query union used by the default
  harness. Query names use only `derived__` and `industry__`.
  Specific evaluation roles remain available in the manifest. It contains the
  complete 170-query core plus all 54 evaluation controls.

- `core/` is the 170-query paper benchmark. Every query is derived from a named
  TPC-H, TPC-DS, JOB, or SQLStorm query skeleton and has a row in
  `manifest.csv`.
- `supplemental/` contains all 28 correct legacy queries for which the pinned
  August 10 result selected OuterYan and measured `tm_speedup > 1.0`. They must
  not be included in an unbiased headline benchmark score and are not
  industry-derived.
- `industry_inspired/` is a 54-query evaluation corpus: nine business-role
  patterns, all 25 completed Graph-generator patterns, and 20 schema-synthetic
  regression guards. Graph membership is complete rather than selected from
  historical speed-up; manifest roles keep all three strata distinct.

The historical corpus is preserved in `../outerjoin_query_old/`. It remains an
input to the auditable Graph/industry/schema control generation and therefore
must not be deleted with the retired compatibility path.
`legacy_classification.csv`
records the disposition of all 254 historical queries. The historical reference run,
`../results/experiment_onoff_20260810_084908.csv`, contains 170 completed cases
and 84 timeouts. The timeouts are removed from the active historical corpus,
listed in `timeout_exclusions.csv`, and preserved under
`../outerjoin_query_timeout/`. The historical generator remains available as
`../gen_queries.py`; it applies the same timeout exclusion list. The historical
query membership, timeout exclusions, and retained wins are pinned in
`../legacy_corpus.py`. The result filename is provenance only; generation does
not read that CSV or require a local `results/` directory.

The earlier FULL-heavy revision excluded 30 queries using August 30 and
September 8 timeout observations. Those observations do not apply after join
labels changed: the SQL, semantics, and execution plans are different.
`active_timeout_exclusions.csv` is therefore empty for
`v1-mixed-graph25-20260925`, and the current active union restores complete family,
shape, and source coverage. `../benchmark_timeouts.py` and
[`active_corpus_coverage.md`](active_corpus_coverage.md) retain the retired
policy only as historical provenance. A new timeout policy, if needed, must be
derived from a complete mixed-v1 run and pinned under a new corpus revision.

The core size is deliberately comparable to the 170 completed legacy cases,
but core membership is not copied from that experiment. It contains 34 source
seeds and five predetermined transformations per seed:

| Source | Seeds | Core queries |
|---|---:|---:|
| TPC-H | 5 | 25 |
| TPC-DS | 7 | 35 |
| JOB | 10 | 50 |
| SQLStorm | 12 | 60 |

## Generation

```bash
# Reproduce v1 (the default).
python3 auto_test/gen_outerjoin_benchmark.py

# Generate the expanded v2 workload without changing v1.
python3 auto_test/gen_outerjoin_benchmark.py --version v2

# Generate the 102-query root-aggregation workload.
python3 auto_test/gen_outerjoin_benchmark.py --version v3
```

Generation is deterministic. For v1 and v2, the script verifies that every core query:

- has at least three relations and at least one outer join;
- uses a connected sequence of source-derived equality predicates;
- contains no cross product (`ON 1=1`);
- uses at least two join kinds, includes at least one outer join, and has one
  plain equality per graph edge;
- stays inside the current applicability envelope (no aggregate, `DISTINCT`,
  or window operator); and
- has an exact manifest entry.

V2 additionally verifies source provenance, paired vectors across selectivity
tiers, and workload-level I/L/R/F balance.

V3 verifies the same source provenance and join balance, plus near-equal
coverage of `COUNT(*)`, `MIN`, `MAX`, and `SUM` (25/26/26/25 queries).
Aggregation is necessarily outside the v1/v2 non-aggregate applicability
condition.

The generated SQL has also been `EXPLAIN`-validated against the local TPC-H,
TPC-DS, and JOB databases with OuterYan both enabled and disabled.

## Mixed transformation variants

For each normalized source skeleton, the generator emits five tree-grouping
variants. The suffixes are retained for continuity with earlier result files;
the manifest's `join_vector` is authoritative. A deterministic blocked rotation
assigns `I/L/R/F` labels independently of measured performance.

| Suffix | Transformation | Purpose |
|---|---|---|
| `ldmx` | primary left-deep mixed tree | Primary left-deep traversal of the fixed graph. |
| `rdmx` | primary right-deep mixed tree | Primary right-deep traversal of the fixed graph. |
| `bmx` | connected bushy mixed tree | Exercise bushy grouping when the graph admits two nontrivial connected root subplans. |
| `bdmx` | secondary connected bushy mixed tree | Use another connected split/orientation of the fixed graph. |
| `alt` | alternate left-deep mixed tree | Replace `bmx` when a true cross-product-free bushy tree is unavailable. |
| `rdax` | secondary right-deep mixed tree | Replace `bdmx` when a true bushy root is structurally unavailable. |
| `rduX` | alternate right-deep mixed tree | Start from the opposite graph side; `X` is a legacy filename label, not the actual join vector. |

The 170-query core comprises 34 `ldmx`, 34 `rdmx`, 22 `bmx`, 22 `bdmx`, 12
`alt`, 12 `rdax`, and 34 `rduX` cases. It contains 46 left-deep, 80
right-deep, and 44 bushy inputs. Its 625 edge occurrences contain 157 INNER
and 156 each LEFT, RIGHT, and FULL. No query uses a single-kind vector.
Regrouped outer joins are independently specified queries; no cross-grouping
semantic-equivalence claim is made.

The transformation extracts a connected subgraph of relation instances,
aliases, and equality edges from the named source query. That graph is fixed
across all variants. Active `ON` clauses retain one plain column equality per
edge and discard unary `ON` conjuncts that would be outside OuterYan's current
envelope. One JOB edge uses a type-compatible column on the same pair of
relations to avoid an implicit cast. Projection and global selection remain
flat and executable. Consequently, the precise claim is **join-graph-derived**,
not semantic equivalence with the complete source query.

Each generated selection is a global `WHERE` predicate evaluated over the
complete join tree, and every conjunct is NULL-rejecting with respect to the
relation it references. NULL-tolerant guards such as `P(x) OR x IS NULL`, as
well as `COALESCE` and `IS [NOT] DISTINCT FROM`, are excluded from the core.
This keeps the performance workload within OuterYan's null-rejection envelope;
separate correctness tests cover safe handling of NULL-tolerant predicates.
Mixed join vectors are assigned without consulting runtime and then checked for
the current applicability envelope. The `predicate_class` manifest value is
`null_rejecting_outeryan_applicable`.

The 54-query evaluation view receives the same graph-preserving mixed-join
normalization. Its two historical aggregate patterns are emitted as detail
projections so v1 remains a non-aggregate structural comparison; v3 supplies
the dedicated, balanced aggregate workload. `supplemental/` remains the exact, unnormalized 28-query legacy-win
view for historical comparison. Historical speedups in the active evaluation
manifest describe source-selection provenance; they do not transfer to the
normalized SQL.

Across the complete 224-query v1 union, the 801 input join-edge occurrences
contain 200 INNER, 201 LEFT, 200 RIGHT, and 200 FULL labels. Thirty-two queries
use only multiple outer-join kinds and 192 combine INNER with outer joins; no
query has a single-kind vector.

## Provenance terminology

Use the following descriptions consistently:

- **Benchmark-derived:** a named source query, version/location, content hash,
  preserved join graph, and declared transformation are present in the
  manifest.
- **Industry-derived:** an actual anonymized production template or trace is
  available internally, together with a stable source identifier and a written
  anonymization/transformation record.
- **Industry-inspired synthetic:** a manually constructed pattern motivated by
  common DBMS behavior but not traceable to a production query.
- **Optimizer stress:** a synthetic case selected to exercise or characterize a
  particular optimizer mechanism.

An industry-inspired synthetic query may model optional dimensions,
late-arriving references, multi-channel reconciliation, or sparse annotations,
provided that relation roles, preservation direction, and the cause of
unmatched tuples are documented. Good performance does not establish industry
provenance. Until a DBMS-X source record exists, the legacy high-speed queries
must be described as synthetic optimizer stress cases, not as real industry
cases.

## Running

The harness retains the `graph/`, `tpch/`, `tpcds/`, and `job/` family layout,
runs at 32 threads by default, and defaults to the complete all-version run:

```bash
bash auto_test/experiment_onoff.sh --all

# v1 only
bash auto_test/experiment_onoff.sh --version v1 --only all

# Full expanded workload (must be generated first).
bash auto_test/experiment_onoff.sh --version v2 --only all

# All benchmark versions plus v3 selectivity-stress, with separate result files.
bash auto_test/experiment_onoff.sh --all
```

## Aggregation v3 design

V3 contains 102 queries. Every one of the 34 TPC-H, TPC-DS, JOB, and SQLStorm
source seeds contributes its deterministic left-deep, right-deep, and third
structural variant. These are paired with global `COUNT(*)`, grouped `MIN`,
grouped `MAX`, and grouped `SUM`. The mix is 42 `COUNT`, 30 `SUM`, 15 `MIN`,
and 15 `MAX`: MIN and MAX split one extremum class equally, while COUNT receives
the largest share and SUM remains a substantial control class. Each of the
three structural slots has the same 14/10/5/5 mix. The fixed weighted schedule
uses only structural slot order; no result or timing file participates in
membership or aggregate-form selection. The source distribution is 15
TPC-H, 21 TPC-DS, 30 JOB, and 36 SQLStorm queries; the execution-schema family
distribution is 27 TPC-H, 33 TPC-DS, and 42 JOB. Across 375 join edges, the
I/L/R/F counts are 94/94/94/93.

Supported root aggregates enter OuterYan candidate construction. They use the
strict aggregate gate (`candidate_total <= 0.90 * baseline_cost`) without the
stretch or low-selectivity tiers. Aggregate pushdown is enabled only for a
cost-selected OuterYan candidate; a rejected candidate remains the exact DuckDB
baseline. Thus v3 measures both conservative plan selection and the realized
effect of pushdown for selected queries.

## Expanded v2 design

V2 uses the same 34 provenance-backed source graphs, five structural slots per
source, and mixed-join assignment as the current v1. It adds three selectivity
tiers while assigning join edges by the same deterministic cyclic rotation
over INNER, LEFT, RIGHT, and FULL.
Across the 170 base structures, the 625 edges contain 157 INNER and 156 each
LEFT, RIGHT, and FULL. A query with at least four edges contains all four join
kinds; shorter vectors contain two or three kinds. This gives both pure
outer-join cases using multiple outer kinds and cases that mix INNER with outer
joins, with no all-FULL or other single-kind main query.
This is a balance over input-expression labels; optimizer simplification and
physical join selection are evaluated rather than assumed.

Each base is instantiated at three hash-sampling tiers on a central join key:
approximately 0.1%, 1%, and 5% of the source-derived anchor domain. A base uses
the same join vector at all three tiers. This produces 510 benchmark-derived
queries. V2 also carries forward all 54 Graph, industry, and schema-synthetic
evaluation controls. Their relations, predicates, and
parentheses are retained while join labels are deterministically rebalanced.
Across all 564 main queries, the 2,051 edge occurrences contain 512 INNER, 513
LEFT, 513 RIGHT, and 513 FULL labels. The benchmark manifest explicitly
distinguishes the 510 source-derived queries from the synthetic controls.

The `pattern_role` manifest field marks star/branch plus alternate, bushy, or
right-start strata as a `v1_advantage_hypothesis`, reflecting the 0916 design
observation. That tag never controls membership: every seed and tree variant
is present at every selectivity tier, and the remaining cases are retained as
`paired_structural_control`. This keeps the workload useful for testing the
low-selectivity hypothesis without constructing a corpus only from favorable
OuterYan cases. SQL comments and the v2 manifests record the source query,
transformation, selectivity tier, modulus, anchor column, and pattern role.

V2 also generates a deliberately separate `job_regressions/` diagnostic view,
which exposes mixed-v2 counterparts of two cases that
regressed in the retired FULL-heavy revision. Those structures remain in the
main benchmark. Their historical speed-ups are provenance only; both current
mixed-v1 and v2 counterparts require fresh measurement.

V3 owns the compact selectivity-stress view: 42 variants of six
metadata-selected mixed v2 counterparts, with two bases per execution family
and two per tree shape across the complete set. Each family contributes one
native benchmark source and one SQLStorm-derived source. Each base appears at 0.025%,
0.05%, 0.2%, 10%, 20%, 50%, and 80%. Membership uses only static metadata and
a fixed salted SHA-256 rank, never timings or speed-ups. It remains a paired
ablation with `headline_eligible=false`, not 42 independent headline samples.

```bash
# Selectivity ablation: plot/report separately from the headline benchmark.
bash auto_test/experiment_onoff.sh --version v3 \
  --corpus-scope selectivity-stress --only all

# Mixed counterparts of the two historical v1 JOB regressions.
bash auto_test/experiment_onoff.sh --version v2 \
  --corpus-scope job-regressions --only job
```

The following component command is for focused diagnostics, not the default
workflow:

```bash
OY_CORPUS=auto_test/outerjoin_benchmark/supplemental \
  bash auto_test/experiment_onoff.sh --only all
```

When reporting the unified result, preserve the two query-name classes. The
nine `industry__` roles are industry-inspired synthetic tests, not production
traces. The 27 legacy performance guards use `derived__`, while their manifest
roles continue to identify them as performance-selected optimizer regression
tests. The union is one benchmark execution, but it must not be described as
wholly industry-derived.
