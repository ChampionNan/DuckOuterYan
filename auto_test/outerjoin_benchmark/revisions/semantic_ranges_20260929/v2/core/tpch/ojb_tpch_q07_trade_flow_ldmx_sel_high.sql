-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: TPC-H Q7 shipment reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpch_q07_period; tier=high; TPC-H Q7 shipment reporting period
-- predicate: l.l_shipdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((supplier s FULL OUTER JOIN lineitem l ON s.s_suppkey = l.l_suppkey) INNER JOIN orders o ON l.l_orderkey = o.o_orderkey) LEFT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) RIGHT OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey)
WHERE l.l_shipdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31';
