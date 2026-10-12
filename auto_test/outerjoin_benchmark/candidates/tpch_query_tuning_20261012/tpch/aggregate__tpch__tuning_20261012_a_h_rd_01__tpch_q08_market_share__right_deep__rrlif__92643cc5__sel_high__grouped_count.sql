-- query_tuning: tpch-query-tuning-20261012; replaces aggregate__tpch__tpch_q08_market_share__right_deep__rrlif__92643cc5__sel_high__grouped_count
-- source: TPC-H Q8
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT p.p_partkey AS group_key, COUNT(*) AS row_count
FROM (part p RIGHT OUTER JOIN (region r RIGHT OUTER JOIN (nation n LEFT OUTER JOIN (customer c INNER JOIN (orders o FULL OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON c.c_nationkey = n.n_nationkey) ON n.n_regionkey = r.r_regionkey) ON p.p_partkey = l.l_partkey)
WHERE o.o_orderdate BETWEEN DATE '1994-02-10' AND DATE '1996-12-31'
GROUP BY p.p_partkey;
