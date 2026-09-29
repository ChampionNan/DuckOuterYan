-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FILR; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FILR; relation and predicate structure unchanged
SELECT *
FROM ((( title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN name n ON ci.person_id = n.id) LEFT OUTER JOIN ( movie_keyword mk RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE ci.person_id <= 1000;
