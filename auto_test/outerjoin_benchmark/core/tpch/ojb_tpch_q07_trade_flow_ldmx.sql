-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
SELECT *
FROM ((((supplier s LEFT OUTER JOIN lineitem l ON s.s_suppkey = l.l_suppkey) FULL OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) RIGHT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) INNER JOIN nation n ON s.s_nationkey = n.n_nationkey)
WHERE (s.s_suppkey % 100 = 0 OR s.s_suppkey IS NULL);
