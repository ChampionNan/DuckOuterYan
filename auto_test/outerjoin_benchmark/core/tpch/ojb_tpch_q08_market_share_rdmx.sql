-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
SELECT *
FROM (region r FULL OUTER JOIN (nation n RIGHT OUTER JOIN (customer c INNER JOIN (orders o LEFT OUTER JOIN (lineitem l FULL OUTER JOIN part p ON p.p_partkey = l.l_partkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON c.c_nationkey = n.n_nationkey) ON n.n_regionkey = r.r_regionkey)
WHERE (p.p_partkey % 1000 = 0 OR p.p_partkey IS NULL);
