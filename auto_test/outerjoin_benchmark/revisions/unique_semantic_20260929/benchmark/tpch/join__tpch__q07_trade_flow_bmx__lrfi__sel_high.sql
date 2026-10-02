-- query_type: join; family: tpch
-- source: TPC-H Q7
-- semantic_filter: tpch_q07_period; tier=high; TPC-H Q7 shipment reporting period
-- predicate: l.l_shipdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((supplier s INNER JOIN nation n ON s.s_nationkey = n.n_nationkey) LEFT OUTER JOIN (lineitem l RIGHT OUTER JOIN (orders o FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON s.s_suppkey = l.l_suppkey)
WHERE l.l_shipdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31';
