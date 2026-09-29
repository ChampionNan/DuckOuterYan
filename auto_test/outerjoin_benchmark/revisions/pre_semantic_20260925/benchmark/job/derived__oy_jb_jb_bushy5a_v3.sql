-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation and predicate structure unchanged
SELECT *
FROM ((( title t INNER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN ( movie_keyword mk FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE mk.keyword_id % 7 <> 0;
