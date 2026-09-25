-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Customer orders are the mandatory backbone and line items provide optional revenue detail.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=o.o_custkey; group_key=c.c_custkey
SELECT COUNT(*) AS row_count
FROM ((customer c LEFT OUTER JOIN orders o ON c.c_custkey = o.o_custkey) RIGHT OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE c.c_custkey % 1000 = 0;
