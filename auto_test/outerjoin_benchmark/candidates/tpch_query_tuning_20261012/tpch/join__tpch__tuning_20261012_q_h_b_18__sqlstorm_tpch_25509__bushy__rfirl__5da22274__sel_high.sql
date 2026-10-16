-- query_tuning: tpch-query-tuning-20261012; replaces join__tpch__sqlstorm_tpch_25509__bushy__rfirl__5da22274__sel_high
-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT p.p_partkey, ps.ps_partkey, ps.ps_suppkey, s.s_suppkey, l.l_partkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey
FROM (((orders o RIGHT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) FULL OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) INNER JOIN (part p RIGHT OUTER JOIN (supplier s LEFT OUTER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey) ON p.p_partkey = l.l_partkey)
WHERE o.o_orderdate BETWEEN DATE '1994-03-30' AND DATE '1996-12-31';
