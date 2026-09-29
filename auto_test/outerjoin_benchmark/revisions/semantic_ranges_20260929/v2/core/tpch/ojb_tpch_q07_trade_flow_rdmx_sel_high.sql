-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: TPC-H Q7 shipment reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpch_q07_period; tier=high; TPC-H Q7 shipment reporting period
-- predicate: l.l_shipdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (nation n FULL OUTER JOIN (customer c RIGHT OUTER JOIN (orders o LEFT OUTER JOIN (lineitem l INNER JOIN supplier s ON s.s_suppkey = l.l_suppkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON s.s_nationkey = n.n_nationkey)
WHERE l.l_shipdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31';
