-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; uniform right-deep LEFT OUTER JOIN control
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
SELECT *
FROM (nation n LEFT OUTER JOIN (customer c LEFT OUTER JOIN (orders o LEFT OUTER JOIN (lineitem l LEFT OUTER JOIN supplier s ON s.s_suppkey = l.l_suppkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON s.s_nationkey = n.n_nationkey)
WHERE s.s_suppkey % 100 = 0;
