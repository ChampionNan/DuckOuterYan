-- query_type: graph; family: tpch
-- source:
-- semantic_filter: tpch_order_date; tier=medium; order booking period
-- predicate: orders.o_orderdate BETWEEN DATE '1994-03-20' AND DATE '1996-03-09'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM customer
    LEFT OUTER JOIN orders   ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    FULL OUTER JOIN nation   ON c_nationkey = n_nationkey
WHERE orders.o_orderdate BETWEEN DATE '1994-03-20' AND DATE '1996-03-09';
