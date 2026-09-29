-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRFI; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRFI; relation graph retained; semantic filter replaced
-- semantic_filter: tpch_order_date; tier=medium; order booking period
-- predicate: orders.o_orderdate BETWEEN DATE '1994-03-20' AND DATE '1996-03-09'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM region LEFT OUTER JOIN (nation RIGHT OUTER JOIN (customer FULL OUTER JOIN (orders INNER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey) ON n_nationkey = c_nationkey) ON r_regionkey = n_regionkey
WHERE orders.o_orderdate BETWEEN DATE '1994-03-20' AND DATE '1996-03-09';
