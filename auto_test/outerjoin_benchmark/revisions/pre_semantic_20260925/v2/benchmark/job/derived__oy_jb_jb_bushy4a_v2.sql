-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
SELECT *
FROM (( title t RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id) FULL OUTER JOIN ( movie_companies mc INNER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE cn.id > 0 AND cn.id < 10000;
