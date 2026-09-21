-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=n.n_nationkey; predicate=hash(anchor) % 100 = 0
SELECT *
FROM (part p FULL OUTER JOIN (lineitem l FULL OUTER JOIN (orders o FULL OUTER JOIN (customer c FULL OUTER JOIN (nation n FULL OUTER JOIN region r ON n.n_regionkey = r.r_regionkey) ON c.c_nationkey = n.n_nationkey) ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON p.p_partkey = l.l_partkey)
WHERE (p.p_partkey % 1000 = 0)
  AND hash(n.n_nationkey) % 100 = 0;
