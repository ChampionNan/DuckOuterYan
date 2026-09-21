-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=o.o_custkey; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM (customer c FULL OUTER JOIN (orders o FULL OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey)
WHERE (c.c_custkey % 1000 = 0)
  AND hash(o.o_custkey) % 1000 = 0;
