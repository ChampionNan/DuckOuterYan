-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation graph retained; semantic filter replaced
-- semantic_filter: tpch_order_date; tier=low; order booking period
-- predicate: orders.o_orderdate BETWEEN DATE '1995-02-08' AND DATE '1995-04-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT c_custkey, c_name, n_name, o_orderdate, l_quantity, l_extendedprice
FROM customer
    INNER JOIN orders   ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    RIGHT OUTER JOIN nation   ON c_nationkey = n_nationkey
    FULL OUTER JOIN region   ON n_regionkey = r_regionkey
WHERE orders.o_orderdate BETWEEN DATE '1995-02-08' AND DATE '1995-04-19';
