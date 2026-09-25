-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((lineitem l RIGHT OUTER JOIN part p ON p.p_partkey = l.l_partkey) FULL OUTER JOIN (orders o INNER JOIN ((nation n LEFT OUTER JOIN customer c ON c.c_nationkey = n.n_nationkey) RIGHT OUTER JOIN region r ON n.n_regionkey = r.r_regionkey) ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey)
WHERE p.p_partkey % 1000 = 0;
