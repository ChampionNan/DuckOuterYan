-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
SELECT *
FROM (lineitem l RIGHT OUTER JOIN (orders o INNER JOIN customer c ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE (c.c_custkey % 1000 = 0 OR c.c_custkey IS NULL);
