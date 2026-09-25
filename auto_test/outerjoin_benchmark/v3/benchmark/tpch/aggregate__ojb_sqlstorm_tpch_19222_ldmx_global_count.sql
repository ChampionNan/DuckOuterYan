-- source: SQLStorm v1.0/tpch/queries/19222.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Part-supplier coverage adapted from SQLStorm: selected parts remain visible when a supply or supplier record is missing.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ps.ps_partkey; group_key=p.p_partkey
SELECT COUNT(*) AS row_count
FROM ((part p INNER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) LEFT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey)
WHERE p.p_partkey <= 1000;
