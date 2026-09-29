-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Supplier-to-customer trade flow with optional order and nation annotations.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=o.o_orderkey; group_key=s.s_suppkey
SELECT COUNT(*) AS row_count
FROM ((((supplier s FULL OUTER JOIN lineitem l ON s.s_suppkey = l.l_suppkey) INNER JOIN orders o ON l.l_orderkey = o.o_orderkey) LEFT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) RIGHT OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey)
WHERE s.s_suppkey % 100 = 0;
