-- query_type: graph; family: tpch
-- source:
-- semantic_filter: tpch_order_date; tier=high; order booking period
-- predicate: orders.o_orderdate BETWEEN DATE '1993-05-24' AND DATE '1997-01-03'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM customer FULL OUTER JOIN (orders INNER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE orders.o_orderdate BETWEEN DATE '1993-05-24' AND DATE '1997-01-03';
