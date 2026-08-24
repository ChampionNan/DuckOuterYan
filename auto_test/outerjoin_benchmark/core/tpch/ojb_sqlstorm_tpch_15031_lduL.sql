-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM ((supplier s FULL OUTER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) FULL OUTER JOIN part p ON p.p_partkey = ps.ps_partkey)
WHERE p.p_partkey % 1000 = 0;
