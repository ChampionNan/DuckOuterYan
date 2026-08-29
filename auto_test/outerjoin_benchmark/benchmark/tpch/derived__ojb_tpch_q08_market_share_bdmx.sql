-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
SELECT *
FROM ((lineitem l FULL OUTER JOIN part p ON p.p_partkey = l.l_partkey) FULL OUTER JOIN (orders o FULL OUTER JOIN ((nation n FULL OUTER JOIN customer c ON c.c_nationkey = n.n_nationkey) FULL OUTER JOIN region r ON n.n_regionkey = r.r_regionkey) ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey)
WHERE p.p_partkey % 1000 = 0;
