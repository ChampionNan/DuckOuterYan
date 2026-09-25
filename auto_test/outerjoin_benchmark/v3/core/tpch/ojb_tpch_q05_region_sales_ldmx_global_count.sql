-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Regional sales in the source date window: retain region-filtered coverage while exposing missing line-item information.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=o.o_custkey; group_key=r.r_regionkey
SELECT COUNT(*) AS row_count
FROM ((((region r INNER JOIN nation n ON r.r_regionkey = n.n_regionkey) LEFT OUTER JOIN customer c ON n.n_nationkey = c.c_nationkey) RIGHT OUTER JOIN orders o ON c.c_custkey = o.o_custkey) FULL OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE r.r_name = 'ASIA' AND o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01';
