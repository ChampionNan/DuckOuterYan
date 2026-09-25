-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
SELECT *
FROM (( title t LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id) RIGHT OUTER JOIN ( movie_companies mc FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE mc.movie_id % 3 = 0;
