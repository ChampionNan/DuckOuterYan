-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (supplier s FULL OUTER JOIN (partsupp ps FULL OUTER JOIN (part p FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE p.p_partkey % 1000 = 0;
