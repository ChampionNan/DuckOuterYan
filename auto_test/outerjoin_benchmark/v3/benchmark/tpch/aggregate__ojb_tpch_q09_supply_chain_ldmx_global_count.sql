-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Part supply coverage: retain selected parts while exposing missing line-item, supplier, supply-record, and order information.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=l.l_suppkey; group_key=p.p_partkey
SELECT COUNT(*) AS row_count
FROM ((((part p INNER JOIN lineitem l ON p.p_partkey = l.l_partkey) LEFT OUTER JOIN supplier s ON l.l_suppkey = s.s_suppkey) RIGHT OUTER JOIN partsupp ps ON ps.ps_suppkey = l.l_suppkey) FULL OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey)
WHERE p.p_name LIKE '%green%';
