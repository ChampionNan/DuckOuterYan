-- source: TPC-H Q9
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: TPC-H Q9 product-name color search, expanded from a shade to a color palette
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpch_part_color; tier=medium; TPC-H Q9 product-name color search, expanded from a shade to a color palette
-- predicate: p.p_name LIKE '%green%'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT p.p_partkey, p.p_name, l.l_orderkey, s.s_suppkey, ps.ps_supplycost, o.o_orderdate
FROM (orders o INNER JOIN (partsupp ps FULL OUTER JOIN (supplier s RIGHT OUTER JOIN (lineitem l LEFT OUTER JOIN part p ON p.p_partkey = l.l_partkey) ON l.l_suppkey = s.s_suppkey) ON ps.ps_suppkey = l.l_suppkey) ON o.o_orderkey = l.l_orderkey)
WHERE p.p_name LIKE '%green%';
