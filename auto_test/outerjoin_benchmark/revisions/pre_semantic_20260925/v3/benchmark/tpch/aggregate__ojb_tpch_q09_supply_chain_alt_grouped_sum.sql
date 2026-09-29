-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=l.l_suppkey; group_key=p.p_partkey
SELECT p.p_partkey AS group_key, SUM(l.l_suppkey) AS key_sum
FROM ((((part p RIGHT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN supplier s ON l.l_suppkey = s.s_suppkey) INNER JOIN partsupp ps ON ps.ps_suppkey = l.l_suppkey) LEFT OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey)
WHERE p.p_name LIKE '%green%'
GROUP BY p.p_partkey;
