-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (((((customer c FULL OUTER JOIN orders o ON o.o_custkey = c.c_custkey) FULL OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN part p ON p.p_partkey = l.l_partkey) FULL OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey)
WHERE p.p_partkey % 1000 = 0;
