-- query_type: join; family: tpch
-- source: TPC-H Q3
-- semantic_filter: tpch_order_deadline; tier=medium; TPC-H Q3 orders booked before a reporting deadline
-- predicate: o.o_orderdate < DATE '1994-01-01'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((customer c LEFT OUTER JOIN orders o ON c.c_custkey = o.o_custkey) RIGHT OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate < DATE '1994-01-01';
