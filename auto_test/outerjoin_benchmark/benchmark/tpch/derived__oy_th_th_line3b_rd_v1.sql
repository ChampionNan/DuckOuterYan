-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RF; relation and predicate structure unchanged
SELECT *
FROM customer RIGHT OUTER JOIN (orders FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey) ON c_custkey = o_custkey
WHERE o_totalprice % 2 = 1;
