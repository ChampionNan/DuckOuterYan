-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: SQLStorm available-stock minimum
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ps.ps_partkey; group_key=p.p_partkey
-- semantic_filter: tpch_stock_available; tier=high; SQLStorm available-stock minimum
-- predicate: ps.ps_availqty > 4000
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM ((part p LEFT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) RIGHT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey)
WHERE ps.ps_availqty > 4000;
