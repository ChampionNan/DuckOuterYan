-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
SELECT *
FROM (customer c FULL OUTER JOIN (orders o FULL OUTER JOIN (lineitem l FULL OUTER JOIN (supplier s FULL OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey) ON s.s_suppkey = l.l_suppkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey)
WHERE s.s_suppkey % 100 = 0;
