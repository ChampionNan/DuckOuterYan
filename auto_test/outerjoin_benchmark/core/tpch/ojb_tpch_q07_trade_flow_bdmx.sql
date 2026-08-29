-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
SELECT *
FROM (((lineitem l FULL OUTER JOIN supplier s ON s.s_suppkey = l.l_suppkey) FULL OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey) FULL OUTER JOIN (customer c FULL OUTER JOIN orders o ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey)
WHERE s.s_suppkey % 100 = 0;
