-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; cross-product-free bushy grouping with mixed join labeling
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
SELECT *
FROM ((supplier s INNER JOIN nation n ON s.s_nationkey = n.n_nationkey) LEFT OUTER JOIN (lineitem l FULL OUTER JOIN (orders o RIGHT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON s.s_suppkey = l.l_suppkey)
WHERE (s.s_suppkey % 100 = 0 OR s.s_suppkey IS NULL);
