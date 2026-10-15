-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__tpch__tpch_q05_region_sales__left_deep__irfl__18fddc7a__sel_high
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM ((((region r FULL OUTER JOIN nation n ON r.r_regionkey = n.n_regionkey) LEFT OUTER JOIN customer c ON n.n_nationkey = c.c_nationkey) RIGHT OUTER JOIN orders o ON c.c_custkey = o.o_custkey) INNER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate >= DATE '1992-01-01' AND o.o_orderdate < DATE '1995-08-01';
