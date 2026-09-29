-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ps.ps_partkey; group_key=p.p_partkey
SELECT COUNT(*) AS row_count
FROM (lineitem l INNER JOIN (supplier s FULL OUTER JOIN (partsupp ps RIGHT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = l.l_partkey)
WHERE p.p_partkey % 1000 = 0;
