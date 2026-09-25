-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM (customer c LEFT OUTER JOIN (orders o INNER JOIN (lineitem l FULL OUTER JOIN (supplier s RIGHT OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey) ON s.s_suppkey = l.l_suppkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey)
WHERE s.s_suppkey % 100 = 0;
