-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=ps.ps_partkey; group_key=p.p_partkey
SELECT p.p_partkey AS group_key, SUM(ps.ps_partkey) AS key_sum
FROM (((part p LEFT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) RIGHT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey)
WHERE p.p_partkey % 1000 = 0
GROUP BY p.p_partkey;
