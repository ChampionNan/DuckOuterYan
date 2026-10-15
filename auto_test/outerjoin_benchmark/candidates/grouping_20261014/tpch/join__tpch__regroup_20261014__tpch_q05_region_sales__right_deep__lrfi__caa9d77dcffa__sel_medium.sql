-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__tpch__tpch_q05_region_sales__right_deep__lifr__e2cece9a__sel_medium
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (region r LEFT OUTER JOIN (lineitem l RIGHT OUTER JOIN (orders o FULL OUTER JOIN (customer c INNER JOIN nation n ON n.n_nationkey = c.c_nationkey) ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey) ON r.r_regionkey = n.n_regionkey)
WHERE o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01';
