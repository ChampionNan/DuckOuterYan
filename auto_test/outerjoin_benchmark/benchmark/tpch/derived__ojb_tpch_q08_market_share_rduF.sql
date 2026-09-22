-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM (part p FULL OUTER JOIN (lineitem l INNER JOIN (orders o LEFT OUTER JOIN (customer c RIGHT OUTER JOIN (nation n FULL OUTER JOIN region r ON n.n_regionkey = r.r_regionkey) ON c.c_nationkey = n.n_nationkey) ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON p.p_partkey = l.l_partkey)
WHERE p.p_partkey % 1000 = 0;
