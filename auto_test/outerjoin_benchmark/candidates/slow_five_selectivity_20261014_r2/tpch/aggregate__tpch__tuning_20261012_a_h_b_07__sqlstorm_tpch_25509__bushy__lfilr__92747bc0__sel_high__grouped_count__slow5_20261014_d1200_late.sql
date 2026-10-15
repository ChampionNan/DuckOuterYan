-- query_tuning: tpch-query-tuning-20261012; replaces aggregate__tpch__sqlstorm_tpch_25509__bushy__lfilr__92747bc0__sel_high__grouped_count
-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT p.p_partkey AS group_key, COUNT(*) AS row_count
FROM (((part p LEFT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) INNER JOIN (customer c LEFT OUTER JOIN (orders o RIGHT OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON p.p_partkey = l.l_partkey)
WHERE o.o_orderdate BETWEEN DATE '1995-04-21' AND DATE '1998-08-02'
GROUP BY p.p_partkey;
