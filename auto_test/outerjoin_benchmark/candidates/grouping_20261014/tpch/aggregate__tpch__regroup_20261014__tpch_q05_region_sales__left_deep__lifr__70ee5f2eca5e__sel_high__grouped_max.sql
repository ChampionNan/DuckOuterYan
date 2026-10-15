-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: aggregate__tpch__tpch_q05_region_sales__left_deep__lrfi__d2d1bccb__sel_high__grouped_max
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT r.r_regionkey AS group_key, MAX(o.o_custkey) AS max_key
FROM ((((nation n LEFT OUTER JOIN customer c ON n.n_nationkey = c.c_nationkey) INNER JOIN orders o ON c.c_custkey = o.o_custkey) FULL OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey) RIGHT OUTER JOIN region r ON r.r_regionkey = n.n_regionkey)
WHERE o.o_orderdate >= DATE '1992-01-01' AND o.o_orderdate < DATE '1995-08-01'
GROUP BY r.r_regionkey;
