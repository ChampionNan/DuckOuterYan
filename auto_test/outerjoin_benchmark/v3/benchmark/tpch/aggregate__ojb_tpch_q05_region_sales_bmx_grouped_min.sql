-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: Regional sales in the source date window: retain region-filtered coverage while exposing missing line-item information.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=o.o_custkey; group_key=r.r_regionkey
SELECT r.r_regionkey AS group_key, MIN(o.o_custkey) AS min_key
FROM ((region r RIGHT OUTER JOIN nation n ON r.r_regionkey = n.n_regionkey) FULL OUTER JOIN (customer c INNER JOIN (orders o LEFT OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey) ON n.n_nationkey = c.c_nationkey)
WHERE r.r_name = 'ASIA' AND o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01'
GROUP BY r.r_regionkey;
