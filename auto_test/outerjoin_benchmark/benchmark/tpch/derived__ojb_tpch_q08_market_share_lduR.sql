-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
SELECT *
FROM (((((region r FULL OUTER JOIN nation n ON n.n_regionkey = r.r_regionkey) FULL OUTER JOIN customer c ON c.c_nationkey = n.n_nationkey) FULL OUTER JOIN orders o ON o.o_custkey = c.c_custkey) FULL OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN part p ON p.p_partkey = l.l_partkey)
WHERE p.p_partkey % 1000 = 0;
