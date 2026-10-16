-- query_tuning: tpch-query-tuning-20261012; replaces join__tpch__sqlstorm_tpch_17751__left_deep__rfi__e00f7290__sel_medium
-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT p.p_partkey, ps.ps_partkey, ps.ps_suppkey, s.s_suppkey, l.l_partkey
FROM (((part p RIGHT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) INNER JOIN lineitem l ON p.p_partkey = l.l_partkey)
WHERE l.l_shipdate BETWEEN DATE '1997-05-06' AND DATE '1997-12-31';
