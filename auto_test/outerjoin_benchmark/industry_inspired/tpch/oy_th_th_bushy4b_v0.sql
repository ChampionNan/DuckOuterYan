-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILR; relation and predicate structure unchanged
SELECT *
FROM (( region INNER JOIN nation ON r_regionkey = n_regionkey) LEFT OUTER JOIN ( supplier RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE ps_supplycost < 200;
