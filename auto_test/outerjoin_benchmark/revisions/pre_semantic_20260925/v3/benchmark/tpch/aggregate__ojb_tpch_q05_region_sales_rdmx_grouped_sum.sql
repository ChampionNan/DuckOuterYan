-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Regional sales in the source date window: retain region-filtered coverage while exposing missing line-item information.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=o.o_custkey; group_key=r.r_regionkey
SELECT r.r_regionkey AS group_key, SUM(o.o_custkey) AS key_sum
FROM (lineitem l INNER JOIN (orders o FULL OUTER JOIN (customer c RIGHT OUTER JOIN (nation n LEFT OUTER JOIN region r ON r.r_regionkey = n.n_regionkey) ON n.n_nationkey = c.c_nationkey) ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE r.r_name = 'ASIA' AND o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01'
GROUP BY r.r_regionkey;
