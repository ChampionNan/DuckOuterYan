-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=ps.ps_partkey; group_key=p.p_partkey
SELECT p.p_partkey AS group_key, SUM(ps.ps_partkey) AS key_sum
FROM (supplier s FULL OUTER JOIN (partsupp ps RIGHT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE p.p_partkey % 1000 = 0
GROUP BY p.p_partkey;
