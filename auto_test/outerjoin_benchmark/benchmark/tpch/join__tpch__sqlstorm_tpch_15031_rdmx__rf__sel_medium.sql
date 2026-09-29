-- query_type: join; family: tpch
-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- semantic_filter: tpch_stock_available; tier=medium; SQLStorm available-stock minimum
-- predicate: ps.ps_availqty > 7000
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (supplier s FULL OUTER JOIN (partsupp ps RIGHT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE ps.ps_availqty > 7000;
