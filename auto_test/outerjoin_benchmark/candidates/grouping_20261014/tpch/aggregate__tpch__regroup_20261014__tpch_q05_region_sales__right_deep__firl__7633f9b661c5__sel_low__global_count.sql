-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: aggregate__tpch__tpch_q05_region_sales__right_deep__lifr__5c2f330c__sel_low__global_count
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT COUNT(*) AS row_count
FROM (lineitem l FULL OUTER JOIN (orders o INNER JOIN (customer c RIGHT OUTER JOIN (nation n LEFT OUTER JOIN region r ON r.r_regionkey = n.n_regionkey) ON n.n_nationkey = c.c_nationkey) ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1994-03-15';
