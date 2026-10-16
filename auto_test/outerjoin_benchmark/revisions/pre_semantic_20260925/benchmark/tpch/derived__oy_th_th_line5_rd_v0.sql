-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRFI; relation and predicate structure unchanged
SELECT *
FROM region LEFT OUTER JOIN (nation RIGHT OUTER JOIN (customer FULL OUTER JOIN (orders INNER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey) ON n_nationkey = c_nationkey) ON r_regionkey = n_regionkey
WHERE o_totalprice < 50000;
