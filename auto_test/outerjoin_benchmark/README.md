# OuterJoin benchmark design

This directory contains a provenance-backed benchmark for outer-join query
optimization. It deliberately separates three workloads:

- `core/` is the 170-query paper benchmark. Every query is derived from a named
  TPC-H, TPC-DS, JOB, or SQLStorm query skeleton and has a row in
  `manifest.csv`.
- `supplemental/` contains synthetic optimizer stress cases retained from the
  earlier DuckOuterYan corpus. Its 22 cases were selected using the pinned
  August 10 performance result and therefore must not be included in an
  unbiased headline benchmark score. They are also not industry-derived.
- `industry_inspired/` contains nine business-role patterns retained from the
  old corpus. They model optional enrichment, sparse dimensions, completeness
  aggregation, and right-preserved master data. They are labeled
  industry-inspired synthetic because no production trace is recorded.

The active historical corpus is preserved in `../outerjoin_query_old/`.
`../outerjoin_query` is a compatibility link to `core/`, so the existing harness
uses the provenance-backed workload by default. `legacy_classification.csv`
records the disposition of all 254 historical queries. The newest complete run,
`../results/experiment_onoff_20260810_084908.csv`, contains 170 completed cases
and 84 timeouts. The timeouts are removed from the active historical corpus,
listed in `timeout_exclusions.csv`, and preserved under
`../outerjoin_query_timeout/`. The historical generator remains available as
`../gen_queries.py`; it applies the same timeout exclusion list.

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
- stays inside the current core applicability envelope (no aggregate,
  `DISTINCT`, or window operator); and
- has an exact manifest entry.

The generated SQL has also been `EXPLAIN`-validated against the local TPC-H,
TPC-DS, and JOB databases with OuterYan both enabled and disabled.

## Transformation variants

For each normalized source skeleton, the generator emits five standard
variants:

| Suffix | Transformation | Purpose |
|---|---|---|
| `ldmx` | left-deep mixed join vector | Primary left-deep test combining mandatory, optional, and reconciliation edges. |
| `rdmx` | right-deep mixed mirror | Preserve `ldmx` semantics while swapping operands and LEFT/RIGHT at every node. |
| `bmx` | connected bushy mixed tree | Exercise bushy grouping when the join graph admits two nontrivial connected root subplans. |
| `alt` | deterministic alternate mixture | Replace `bmx` when a three-relation or star skeleton cannot form a true bushy tree without a cross product. |
| `lduX` / `rduX` | uniform left-/right-deep control, where `X` is `L`, `R`, or `F` | Isolate a single outer-join kind while balancing LEFT, RIGHT, and FULL coverage. |

`ldmx` and `rdmx` have the same relational semantics: operand exchange also
exchanges LEFT and RIGHT, while INNER and FULL remain unchanged. Their paired
results directly test join direction and child orientation. A `bmx` query is
not claimed to be equivalent, because regrouping outer joins can change query
semantics.

The 170-query core contains 102 mixed-join queries and 68 uniform controls. The
mixed population comprises 34 `ldmx`, 34 `rdmx`, 22 `bmx`, and 12 structurally
necessary `alt` cases. Uniform controls comprise 34 left-deep and 34 right-deep
queries, with the join kinds distributed 23 LEFT, 23 RIGHT, and 22 FULL. Thus,
mixed joins are the main workload rather than an auxiliary variant.

The transformation extracts a connected subgraph of relation instances,
aliases, and equality predicates from the named source query. That subgraph is
fixed across all variants of the seed. Projection and selection are normalized
to remain executable as a flat optimizer test. Consequently, the precise claim
is **join-skeleton-derived**, not a claim that the complete original benchmark
query is semantically equivalent after its inner joins become outer joins.

Each generated selection is a global `WHERE` predicate evaluated over the
complete join tree, and every conjunct is NULL-rejecting with respect to the
relation it references. NULL-tolerant guards such as `P(x) OR x IS NULL`, as
well as `COALESCE` and `IS [NOT] DISTINCT FROM`, are excluded from the core.
This keeps the performance workload within OuterYan's null-rejection envelope;
separate correctness tests cover safe handling of NULL-tolerant predicates.
The `predicate_class` manifest column marks every core entry as
`null_rejecting`.

Shape and join-vector labels describe the input SQL before semantic
simplification. A global NULL-rejecting predicate can legitimately collapse an
enclosing outer join; those cases exercise outer-join simplification, whereas
the remaining cases continue into outer-join enumeration and execution.

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

The core retains the harness's `tpch/`, `tpcds/`, and `job/` family layout:

```bash
OY_CORPUS=auto_test/outerjoin_benchmark/core \
  bash auto_test/experiment_onoff.sh --only bench
```

Run the supplemental workload separately:

```bash
OY_CORPUS=auto_test/outerjoin_benchmark/supplemental \
  bash auto_test/experiment_onoff.sh --only all
```

Do not merge core and supplemental results into one benchmark aggregate. Report
the core by source, topology, join labeling, and relation count; report the
supplemental suite as optimizer characterization.

Run the industry-inspired component separately:

```bash
OY_CORPUS=auto_test/outerjoin_benchmark/industry_inspired \
  bash auto_test/experiment_onoff.sh --only bench
```

Report this component as industry-inspired synthetic testing, separately from
both the benchmark-derived core and the performance-selected stress suite.
