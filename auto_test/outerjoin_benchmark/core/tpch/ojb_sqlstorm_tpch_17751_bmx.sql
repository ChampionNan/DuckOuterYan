-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; cross-product-free bushy grouping with mixed join labeling
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM ((part p RIGHT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) LEFT OUTER JOIN (partsupp ps FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey)
WHERE (p.p_partkey % 1000 = 0 OR p.p_partkey IS NULL);
