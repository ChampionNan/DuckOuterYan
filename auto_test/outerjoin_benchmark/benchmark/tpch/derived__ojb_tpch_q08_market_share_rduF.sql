-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
SELECT *
FROM (part p FULL OUTER JOIN (lineitem l FULL OUTER JOIN (orders o FULL OUTER JOIN (customer c FULL OUTER JOIN (nation n FULL OUTER JOIN region r ON n.n_regionkey = r.r_regionkey) ON c.c_nationkey = n.n_nationkey) ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON p.p_partkey = l.l_partkey)
WHERE p.p_partkey % 1000 = 0;
