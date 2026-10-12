-- query_tuning: tpch-query-tuning-20261012; replaces aggregate__tpch__tpch_q07_trade_flow__right_deep__irfl__06dcfc3b__sel_high__grouped_count
-- source: TPC-H Q7
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT s.s_suppkey AS group_key, COUNT(*) AS row_count
FROM (nation n INNER JOIN (supplier s RIGHT OUTER JOIN (customer c FULL OUTER JOIN (orders o LEFT OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON s.s_suppkey = l.l_suppkey) ON s.s_nationkey = n.n_nationkey)
WHERE l.l_shipdate BETWEEN DATE '1994-03-30' AND DATE '1996-12-31'
GROUP BY s.s_suppkey;
