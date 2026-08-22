-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
SELECT *
FROM ((customer c INNER JOIN orders o ON c.c_custkey = o.o_custkey) LEFT OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE c.c_custkey % 1000 = 0;
