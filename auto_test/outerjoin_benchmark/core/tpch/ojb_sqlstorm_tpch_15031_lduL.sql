-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- transformation: connected join-subgraph adaptation; uniform left-deep LEFT OUTER JOIN control
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM ((part p LEFT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) LEFT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey)
WHERE (p.p_partkey % 1000 = 0 OR p.p_partkey IS NULL);
