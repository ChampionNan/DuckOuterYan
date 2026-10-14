-- query_tuning: tpch-query-tuning-20261012; replaces join__tpch__sqlstorm_tpch_17751__bushy__rfi__4cf6bc5f__sel_low
-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT p.p_partkey, ps.ps_partkey, ps.ps_suppkey, s.s_suppkey, l.l_partkey
FROM ((part p RIGHT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN (supplier s INNER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey)
WHERE l.l_shipdate BETWEEN DATE '1997-11-14' AND DATE '1997-12-31';
