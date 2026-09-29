-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: IL; relation graph retained; semantic filter replaced
-- semantic_filter: tpch_order_date; tier=high; order booking period
-- predicate: orders.o_orderdate BETWEEN DATE '1993-05-24' AND DATE '1997-01-03'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM customer INNER JOIN (orders LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE orders.o_orderdate BETWEEN DATE '1993-05-24' AND DATE '1997-01-03';
