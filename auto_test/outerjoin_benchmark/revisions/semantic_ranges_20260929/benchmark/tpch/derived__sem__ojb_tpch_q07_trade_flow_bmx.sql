-- source: TPC-H Q7
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: TPC-H Q7 shipment reporting period
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpch_q07_period; tier=medium; TPC-H Q7 shipment reporting period
-- predicate: l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((supplier s INNER JOIN nation n ON s.s_nationkey = n.n_nationkey) LEFT OUTER JOIN (lineitem l RIGHT OUTER JOIN (orders o FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON s.s_suppkey = l.l_suppkey)
WHERE l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31';
