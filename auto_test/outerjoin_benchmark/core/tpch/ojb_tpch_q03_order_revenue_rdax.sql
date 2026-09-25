-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM (lineitem l LEFT OUTER JOIN (customer c INNER JOIN orders o ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE c.c_custkey % 1000 = 0;
