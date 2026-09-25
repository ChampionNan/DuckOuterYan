-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ps.ps_partkey; group_key=p.p_partkey
SELECT COUNT(*) AS row_count
FROM ((part p LEFT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) RIGHT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey)
WHERE p.p_partkey % 1000 = 0;
