-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: SQLStorm available-stock minimum
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpch_stock_available; tier=high; SQLStorm available-stock minimum
-- predicate: ps.ps_availqty > 4000
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (part p LEFT OUTER JOIN (partsupp ps RIGHT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey)
WHERE ps.ps_availqty > 4000;
