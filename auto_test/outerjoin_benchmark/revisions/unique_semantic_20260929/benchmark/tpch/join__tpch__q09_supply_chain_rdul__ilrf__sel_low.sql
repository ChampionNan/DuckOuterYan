-- query_type: join; family: tpch
-- source: TPC-H Q9
-- semantic_filter: tpch_part_color; tier=low; TPC-H Q9 product-name color search, expanded from a shade to a color palette
-- predicate: p.p_name LIKE '%forest green%'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM (part p INNER JOIN (supplier s LEFT OUTER JOIN (partsupp ps RIGHT OUTER JOIN (lineitem l FULL OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey) ON ps.ps_suppkey = l.l_suppkey) ON l.l_suppkey = s.s_suppkey) ON p.p_partkey = l.l_partkey)
WHERE p.p_name LIKE '%forest green%';
