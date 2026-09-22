-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILR; relation and predicate structure unchanged
SELECT *
FROM (( title t INNER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN ( movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE mc.movie_id % 3 = 0;
