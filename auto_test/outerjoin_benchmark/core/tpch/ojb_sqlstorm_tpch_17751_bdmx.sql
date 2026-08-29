-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM ((supplier s FULL OUTER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) FULL OUTER JOIN (lineitem l FULL OUTER JOIN part p ON p.p_partkey = l.l_partkey) ON p.p_partkey = ps.ps_partkey)
WHERE p.p_partkey % 1000 = 0;
