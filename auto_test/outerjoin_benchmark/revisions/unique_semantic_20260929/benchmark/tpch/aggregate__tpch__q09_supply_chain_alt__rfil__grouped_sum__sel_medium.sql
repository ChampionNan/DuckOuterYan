-- query_type: aggregate; family: tpch
-- source: TPC-H Q9
-- semantic_filter: tpch_part_color; tier=medium; TPC-H Q9 product-name color search, expanded from a shade to a color palette
-- predicate: p.p_name LIKE '%green%'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT p.p_partkey AS group_key, SUM(l.l_suppkey) AS key_sum
FROM ((((part p RIGHT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN supplier s ON l.l_suppkey = s.s_suppkey) INNER JOIN partsupp ps ON ps.ps_suppkey = l.l_suppkey) LEFT OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey)
WHERE p.p_name LIKE '%green%'
GROUP BY p.p_partkey;
