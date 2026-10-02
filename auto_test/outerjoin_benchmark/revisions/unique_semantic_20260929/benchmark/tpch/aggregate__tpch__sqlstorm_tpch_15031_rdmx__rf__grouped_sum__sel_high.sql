-- query_type: aggregate; family: tpch
-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- semantic_filter: tpch_stock_available; tier=high; SQLStorm available-stock minimum
-- predicate: ps.ps_availqty > 4000
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT p.p_partkey AS group_key, SUM(ps.ps_partkey) AS key_sum
FROM (supplier s FULL OUTER JOIN (partsupp ps RIGHT OUTER JOIN part p ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE ps.ps_availqty > 4000
GROUP BY p.p_partkey;
