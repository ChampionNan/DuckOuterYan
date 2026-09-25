-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM (((lineitem l RIGHT OUTER JOIN supplier s ON s.s_suppkey = l.l_suppkey) LEFT OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey) FULL OUTER JOIN (customer c INNER JOIN orders o ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey)
WHERE s.s_suppkey % 100 = 0;
