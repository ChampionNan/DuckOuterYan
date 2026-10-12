-- query_tuning: tpch-query-tuning-20261012; replaces aggregate__tpch__sqlstorm_tpch_17751__bushy__lfi__110205d2__sel_high__global_count
-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT COUNT(*) AS row_count
FROM ((supplier s INNER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) RIGHT OUTER JOIN (part p FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) ON p.p_partkey = ps.ps_partkey)
WHERE l.l_shipdate BETWEEN DATE '1995-03-30' AND DATE '1997-12-31';
