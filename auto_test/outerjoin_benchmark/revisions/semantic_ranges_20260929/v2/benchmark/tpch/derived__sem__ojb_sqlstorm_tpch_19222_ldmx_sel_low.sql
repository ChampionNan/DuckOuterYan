-- source: SQLStorm v1.0/tpch/queries/19222.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: SQLStorm available-stock minimum
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: tpch_stock_available; tier=low; SQLStorm available-stock minimum
-- predicate: ps.ps_availqty > 9700
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT p.p_name, s.s_name, ps.ps_availqty
FROM ((part p INNER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) LEFT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey)
WHERE ps.ps_availqty > 9700;
