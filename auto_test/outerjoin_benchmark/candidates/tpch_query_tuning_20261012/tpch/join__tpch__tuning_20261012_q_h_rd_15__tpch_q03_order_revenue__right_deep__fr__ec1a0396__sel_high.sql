-- query_tuning: tpch-query-tuning-20261012; replaces join__tpch__tpch_q03_order_revenue__right_deep__fl__78dde91b__sel_high
-- source: TPC-H Q3
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT c.c_custkey, o.o_custkey, o.o_orderkey, l.l_orderkey
FROM (customer c FULL OUTER JOIN (lineitem l RIGHT OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey)
WHERE o.o_orderdate BETWEEN DATE '1992-01-03' AND DATE '1994-10-06';
