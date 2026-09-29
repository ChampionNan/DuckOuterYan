-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=o.o_orderkey; group_key=s.s_suppkey
SELECT s.s_suppkey AS group_key, SUM(o.o_orderkey) AS key_sum
FROM ((supplier s INNER JOIN nation n ON s.s_nationkey = n.n_nationkey) LEFT OUTER JOIN (lineitem l RIGHT OUTER JOIN (orders o FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON s.s_suppkey = l.l_suppkey)
WHERE s.s_suppkey % 100 = 0
GROUP BY s.s_suppkey;
