-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: aggregate__tpch__tpch_q05_region_sales__right_deep__lifr__5c2f330c__sel_high__global_count
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT COUNT(*) AS row_count
FROM (lineitem l RIGHT OUTER JOIN (orders o FULL OUTER JOIN (customer c LEFT OUTER JOIN (nation n INNER JOIN region r ON r.r_regionkey = n.n_regionkey) ON n.n_nationkey = c.c_nationkey) ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate >= DATE '1992-01-01' AND o.o_orderdate < DATE '1995-08-01';
