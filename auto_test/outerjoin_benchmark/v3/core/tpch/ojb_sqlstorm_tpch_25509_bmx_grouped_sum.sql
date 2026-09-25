-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A SQLStorm tpch query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=o.o_orderkey; group_key=p.p_partkey
SELECT p.p_partkey AS group_key, SUM(o.o_orderkey) AS key_sum
FROM ((part p RIGHT OUTER JOIN (partsupp ps FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey) INNER JOIN (lineitem l LEFT OUTER JOIN (orders o RIGHT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON p.p_partkey = l.l_partkey)
WHERE p.p_partkey % 1000 = 0
GROUP BY p.p_partkey;
