# OuterJoin benchmark design

This directory contains one provenance-backed benchmark for outer-join query
optimization plus three auditable component views:

- `benchmark/` is the active 206-query union used by `../outerjoin_query` and
  the default harness. Query names use only `derived__` and `industry__`.
  Specific evaluation roles remain available in the manifest.

- `core/` is the 170-query paper benchmark. Every query is derived from a named
  TPC-H, TPC-DS, JOB, or SQLStorm query skeleton and has a row in
  `manifest.csv`.
- `supplemental/` contains all 28 correct legacy queries for which the pinned
  August 10 result selected OuterYan and measured `tm_speedup > 1.0`. They must
  not be included in an unbiased headline benchmark score and are not
  industry-derived.
- `industry_inspired/` is a 36-query evaluation corpus: the union of nine
  business-role patterns and those 28 legacy performance wins, with one query
  in both groups. Manifest roles keep industry-inspired synthetic patterns
  distinct from performance-selected optimizer stress cases.

The historical corpus is preserved in `../outerjoin_query_old/`.
`../outerjoin_query` is a compatibility link to `benchmark/`.
`legacy_classification.csv`
records the disposition of all 254 historical queries. The newest complete run,
`../results/experiment_onoff_20260810_084908.csv`, contains 170 completed cases
and 84 timeouts. The timeouts are removed from the active historical corpus,
listed in `timeout_exclusions.csv`, and preserved under
`../outerjoin_query_timeout/`. The historical generator remains available as
`../gen_queries.py`; it applies the same timeout exclusion list. The historical
query membership, timeout exclusions, and retained wins are pinned in
`../legacy_corpus.py`. The result filename is provenance only; generation does
not read that CSV or require a local `results/` directory.

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
python3 auto_test/gen_outerjoin_benchmark.py
```

Generation is deterministic. The script verifies that every core query:

- has at least three relations and at least one outer join;
- uses a connected sequence of source-derived equality predicates;
- contains no cross product (`ON 1=1`);
- uses `FULL OUTER JOIN` in every primary/control slot (the `alt` slot is an
  applicability-checked mixed vector), with one plain equality per graph edge;
- stays inside the current applicability envelope (no aggregate, `DISTINCT`,
  or window operator); and
- has an exact manifest entry.

The generated SQL has also been `EXPLAIN`-validated against the local TPC-H,
TPC-DS, and JOB databases with OuterYan both enabled and disabled.

## Transformation variants

For each normalized source skeleton, the generator emits five tree-grouping
variants. The suffixes are retained for continuity with earlier result files;
the manifest's `join_vector` is authoritative. Primary/control slots are
all-`F`, while the structurally necessary `alt` slot remains mixed.

| Suffix | Transformation | Purpose |
|---|---|---|
| `ldmx` | primary left-deep FULL tree | Primary left-deep traversal of the fixed graph. |
| `rdmx` | primary right-deep FULL tree | Primary right-deep traversal of the fixed graph. |
| `bmx` | connected bushy FULL tree | Exercise bushy grouping when the graph admits two nontrivial connected root subplans. |
| `bdmx` | secondary connected bushy FULL tree | Use another connected split/orientation of the fixed graph. |
| `alt` | alternate left-deep mixed tree | Replace `bmx` when a true cross-product-free bushy tree is unavailable. |
| `rdax` | secondary right-deep FULL tree | Replace `bdmx` when a true bushy root is structurally unavailable. |
| `rduX` | alternate right-deep FULL tree | Start from the opposite graph side; `X` is a legacy filename label and the manifest still records an all-`F` vector. |

The 170-query core comprises 34 `ldmx`, 34 `rdmx`, 22 `bmx`, 22 `bdmx`, 12
`alt`, 12 `rdax`, and 34 `rduX` cases. The 158 non-`alt` entries are all-FULL;
the 12 `alt` entries retain mixed labels. It contains 46 left-deep, 80
right-deep, and 44 bushy inputs. Regrouped outer joins are independently
specified queries; no cross-grouping semantic-equivalence claim is made.

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
Primary/control joins are initially FULL so filter pushdown may simplify
direction without collapsing the complete graph to a pure inner query; the 12
mixed `alt` cases are separately applicability-checked. The `predicate_class`
manifest value is `null_rejecting_outeryan_applicable`.

The 36-query evaluation view receives the same graph-preserving FULL-join
normalization. Its two historical aggregate patterns are emitted as detail
projections because the active optimizer deliberately bypasses aggregate
queries. `supplemental/` remains the exact, unnormalized 28-query legacy-win
view for historical comparison. Historical speedups in the active evaluation
manifest describe source-selection provenance; they do not transfer to the
normalized SQL.

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

The active benchmark retains the harness's `graph/`, `tpch/`, `tpcds/`, and
`job/` family layout and runs once:

```bash
OY_CORPUS=auto_test/outerjoin_query \
  bash auto_test/experiment_onoff.sh --only all
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
