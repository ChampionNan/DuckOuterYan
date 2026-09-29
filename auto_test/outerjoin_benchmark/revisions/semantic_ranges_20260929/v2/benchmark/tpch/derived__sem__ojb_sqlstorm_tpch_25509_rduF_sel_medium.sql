-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: SQLStorm 25509 order reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: sqlstorm_order_period; tier=medium; SQLStorm 25509 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (supplier s LEFT OUTER JOIN (partsupp ps INNER JOIN (part p RIGHT OUTER JOIN (lineitem l FULL OUTER JOIN (orders o INNER JOIN customer c ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON p.p_partkey = l.l_partkey) ON p.p_partkey = ps.ps_partkey) ON ps.ps_suppkey = s.s_suppkey)
WHERE o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-12-31';
