-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((customer c FULL OUTER JOIN orders o ON c.c_custkey = o.o_custkey) INNER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE c.c_custkey % 1000 = 0;
