-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=n.n_nationkey; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM (((((part p FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) FULL OUTER JOIN nation n ON c.c_nationkey = n.n_nationkey) FULL OUTER JOIN region r ON n.n_regionkey = r.r_regionkey)
WHERE (p.p_partkey % 1000 = 0)
  AND hash(n.n_nationkey) % 1000 = 0;
