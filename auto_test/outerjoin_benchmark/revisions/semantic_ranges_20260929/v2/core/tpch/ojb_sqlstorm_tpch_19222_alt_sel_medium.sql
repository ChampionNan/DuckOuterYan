-- source: SQLStorm v1.0/tpch/queries/19222.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: SQLStorm available-stock minimum
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: tpch_stock_available; tier=medium; SQLStorm available-stock minimum
-- predicate: ps.ps_availqty > 7000
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT p.p_name, s.s_name, ps.ps_availqty
FROM ((part p RIGHT OUTER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey)
WHERE ps.ps_availqty > 7000;
