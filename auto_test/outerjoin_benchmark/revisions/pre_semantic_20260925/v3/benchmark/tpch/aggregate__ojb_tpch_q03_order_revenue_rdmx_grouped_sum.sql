-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=o.o_custkey; group_key=c.c_custkey
SELECT c.c_custkey AS group_key, SUM(o.o_custkey) AS key_sum
FROM (lineitem l FULL OUTER JOIN (orders o RIGHT OUTER JOIN customer c ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE c.c_custkey % 1000 = 0
GROUP BY c.c_custkey;
