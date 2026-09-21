-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=o.o_custkey; predicate=hash(anchor) % 100 = 0
SELECT *
FROM ((customer c FULL OUTER JOIN orders o ON c.c_custkey = o.o_custkey) FULL OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE (c.c_custkey % 1000 = 0)
  AND hash(o.o_custkey) % 100 = 0;
