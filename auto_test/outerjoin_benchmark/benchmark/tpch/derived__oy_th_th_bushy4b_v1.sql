-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
SELECT *
FROM (( region LEFT OUTER JOIN nation ON r_regionkey = n_regionkey) RIGHT OUTER JOIN ( supplier FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE n_nationkey < 50000;
