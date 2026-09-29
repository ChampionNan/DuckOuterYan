-- query_type: join; family: tpch
-- source: TPC-H Q7
-- semantic_filter: tpch_q07_period; tier=medium; TPC-H Q7 shipment reporting period
-- predicate: l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((lineitem l RIGHT OUTER JOIN supplier s ON s.s_suppkey = l.l_suppkey) LEFT OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey) FULL OUTER JOIN (customer c INNER JOIN orders o ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey)
WHERE l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31';
