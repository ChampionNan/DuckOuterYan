-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
SELECT *
FROM (( region RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey) FULL OUTER JOIN ( supplier INNER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE ps_supplycost < 200;
