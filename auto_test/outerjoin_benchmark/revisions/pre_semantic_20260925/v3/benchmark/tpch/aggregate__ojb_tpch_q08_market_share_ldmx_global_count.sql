-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Part-to-region market coverage through line items, orders, customers, and geography.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=n.n_nationkey; group_key=p.p_partkey
SELECT COUNT(*) AS row_count
FROM (((((part p FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) INNER JOIN orders o ON l.l_orderkey = o.o_orderkey) LEFT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) RIGHT OUTER JOIN nation n ON c.c_nationkey = n.n_nationkey) FULL OUTER JOIN region r ON n.n_regionkey = r.r_regionkey)
WHERE p.p_partkey % 1000 = 0;
