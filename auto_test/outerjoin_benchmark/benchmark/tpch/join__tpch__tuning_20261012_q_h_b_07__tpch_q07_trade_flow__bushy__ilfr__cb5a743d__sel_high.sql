-- query_tuning: tpch-query-tuning-20261012; replaces join__tpch__tpch_q07_trade_flow__bushy__ilfr__cb5a743d__sel_high
-- source: TPC-H Q7
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT s.s_suppkey, l.l_suppkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey, s.s_nationkey, n.n_nationkey
FROM ((supplier s INNER JOIN nation n ON s.s_nationkey = n.n_nationkey) LEFT OUTER JOIN (customer c FULL OUTER JOIN (orders o RIGHT OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON s.s_suppkey = l.l_suppkey)
WHERE l.l_shipdate BETWEEN DATE '1994-03-30' AND DATE '1996-12-31';
