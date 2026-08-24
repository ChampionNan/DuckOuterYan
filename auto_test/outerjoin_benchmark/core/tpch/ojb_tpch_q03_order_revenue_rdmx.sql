-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
SELECT *
FROM (lineitem l FULL OUTER JOIN (orders o FULL OUTER JOIN customer c ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE c.c_custkey % 1000 = 0;
