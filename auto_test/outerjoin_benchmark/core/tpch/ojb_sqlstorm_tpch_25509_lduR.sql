-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- transformation: connected join-subgraph adaptation; uniform left-deep RIGHT OUTER JOIN control
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (((((part p RIGHT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) RIGHT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) RIGHT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) RIGHT OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) RIGHT OUTER JOIN customer c ON o.o_custkey = c.c_custkey)
WHERE (p.p_partkey % 1000 = 0 OR p.p_partkey IS NULL);
