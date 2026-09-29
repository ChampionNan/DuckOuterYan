-- source: SQLStorm v1.0/tpch/queries/19222.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Part-supplier coverage adapted from SQLStorm: selected parts remain visible when a supply or supplier record is missing.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=ps.ps_partkey; group_key=p.p_partkey
SELECT p.p_partkey AS group_key, SUM(ps.ps_partkey) AS key_sum
FROM (supplier s RIGHT OUTER JOIN (partsupp ps LEFT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE p.p_partkey <= 1000
GROUP BY p.p_partkey;
