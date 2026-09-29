-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: SQLStorm 25509 order reporting period
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: sqlstorm_order_period; tier=medium; SQLStorm 25509 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((part p LEFT OUTER JOIN ((orders o RIGHT OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) ON p.p_partkey = l.l_partkey) FULL OUTER JOIN (supplier s INNER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey)
WHERE o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-12-31';
