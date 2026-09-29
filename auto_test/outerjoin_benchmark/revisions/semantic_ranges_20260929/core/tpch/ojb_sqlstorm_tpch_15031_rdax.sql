-- source: SQLStorm v1.0/tpch/queries/15031.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: SQLStorm available-stock minimum
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpch_stock_available; tier=high; SQLStorm available-stock minimum
-- predicate: ps.ps_availqty > 4000
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (supplier s LEFT OUTER JOIN (part p INNER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE ps.ps_availqty > 4000;
