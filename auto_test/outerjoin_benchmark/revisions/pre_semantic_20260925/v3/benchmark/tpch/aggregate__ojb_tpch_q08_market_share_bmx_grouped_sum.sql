-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=n.n_nationkey; group_key=p.p_partkey
SELECT p.p_partkey AS group_key, SUM(n.n_nationkey) AS key_sum
FROM ((part p LEFT OUTER JOIN (lineitem l RIGHT OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) ON p.p_partkey = l.l_partkey) FULL OUTER JOIN (customer c INNER JOIN (nation n LEFT OUTER JOIN region r ON n.n_regionkey = r.r_regionkey) ON c.c_nationkey = n.n_nationkey) ON o.o_custkey = c.c_custkey)
WHERE p.p_partkey % 1000 = 0
GROUP BY p.p_partkey;
