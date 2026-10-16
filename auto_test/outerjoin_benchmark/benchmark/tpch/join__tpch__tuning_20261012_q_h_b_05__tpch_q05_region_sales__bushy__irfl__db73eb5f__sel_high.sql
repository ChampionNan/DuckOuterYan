-- query_tuning: tpch-query-tuning-20261012; replaces join__tpch__tpch_q05_region_sales__bushy__rfil__7700e53e__sel_high
-- source: TPC-H Q5
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM ((region r INNER JOIN nation n ON r.r_regionkey = n.n_regionkey) RIGHT OUTER JOIN (lineitem l FULL OUTER JOIN (orders o LEFT OUTER JOIN customer c ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey) ON n.n_nationkey = c.c_nationkey)
WHERE o.o_orderdate BETWEEN DATE '1992-10-28' AND DATE '1995-08-01';
