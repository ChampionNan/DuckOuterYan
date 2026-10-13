-- query_tuning: tpch-query-tuning-20261012; replaces aggregate__tpch__tpch_q07_trade_flow__left_deep__lrfi__e001d276__sel_high__grouped_count
-- source: TPC-H Q7
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT s.s_suppkey AS group_key, COUNT(*) AS row_count
FROM ((((supplier s LEFT OUTER JOIN lineitem l ON s.s_suppkey = l.l_suppkey) RIGHT OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) INNER JOIN nation n ON s.s_nationkey = n.n_nationkey)
WHERE l.l_shipdate BETWEEN DATE '1994-03-30' AND DATE '1996-12-31'
GROUP BY s.s_suppkey;
