-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer applicability form
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=o.o_custkey; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (lineitem l FULL OUTER JOIN (customer c FULL OUTER JOIN orders o ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE (c.c_custkey % 1000 = 0)
  AND hash(o.o_custkey) % 20 = 0;
