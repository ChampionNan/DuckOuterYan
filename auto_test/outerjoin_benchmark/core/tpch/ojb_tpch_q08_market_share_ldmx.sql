-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
SELECT *
FROM (((((part p FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) RIGHT OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) INNER JOIN customer c ON o.o_custkey = c.c_custkey) LEFT OUTER JOIN nation n ON c.c_nationkey = n.n_nationkey) FULL OUTER JOIN region r ON n.n_regionkey = r.r_regionkey)
WHERE (p.p_partkey % 1000 = 0 OR p.p_partkey IS NULL);
