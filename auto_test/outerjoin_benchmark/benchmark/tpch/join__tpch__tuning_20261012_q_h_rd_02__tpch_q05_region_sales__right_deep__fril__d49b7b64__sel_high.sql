-- query_tuning: tpch-query-tuning-20261012; replaces join__tpch__tpch_q05_region_sales__right_deep__irlf__82e40ee5__sel_high
-- source: TPC-H Q5
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (region r FULL OUTER JOIN (lineitem l RIGHT OUTER JOIN (orders o INNER JOIN (customer c LEFT OUTER JOIN nation n ON n.n_nationkey = c.c_nationkey) ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey) ON r.r_regionkey = n.n_regionkey)
WHERE o.o_orderdate BETWEEN DATE '1992-10-28' AND DATE '1995-08-01';
