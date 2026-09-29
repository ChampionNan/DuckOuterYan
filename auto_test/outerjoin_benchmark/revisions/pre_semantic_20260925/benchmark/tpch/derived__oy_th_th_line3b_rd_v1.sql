-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: IL; relation and predicate structure unchanged
SELECT *
FROM customer INNER JOIN (orders LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE o_totalprice % 2 = 1;
