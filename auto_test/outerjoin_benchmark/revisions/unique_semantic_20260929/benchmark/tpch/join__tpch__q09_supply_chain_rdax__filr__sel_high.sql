-- query_type: join; family: tpch
-- source: TPC-H Q9
-- semantic_filter: tpch_part_color; tier=high; TPC-H Q9 product-name color search, expanded from a shade to a color palette
-- predicate: (p.p_name LIKE '%green%' OR p.p_name LIKE '%blue%' OR p.p_name LIKE '%red%' OR p.p_name LIKE '%yellow%' OR p.p_name LIKE '%orange%' OR p.p_name LIKE '%purple%' OR p.p_name LIKE '%white%' OR p.p_name LIKE '%black%' OR p.p_name LIKE '%pink%' OR p.p_name LIKE '%brown%' OR p.p_name LIKE '%gray%')
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM (orders o RIGHT OUTER JOIN (partsupp ps LEFT OUTER JOIN (part p FULL OUTER JOIN (lineitem l INNER JOIN supplier s ON l.l_suppkey = s.s_suppkey) ON p.p_partkey = l.l_partkey) ON ps.ps_suppkey = l.l_suppkey) ON o.o_orderkey = l.l_orderkey)
WHERE (p.p_name LIKE '%green%' OR p.p_name LIKE '%blue%' OR p.p_name LIKE '%red%' OR p.p_name LIKE '%yellow%' OR p.p_name LIKE '%orange%' OR p.p_name LIKE '%purple%' OR p.p_name LIKE '%white%' OR p.p_name LIKE '%black%' OR p.p_name LIKE '%pink%' OR p.p_name LIKE '%brown%' OR p.p_name LIKE '%gray%');
