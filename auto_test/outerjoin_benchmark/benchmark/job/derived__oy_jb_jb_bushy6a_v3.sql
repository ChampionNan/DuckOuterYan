-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRFIL; relation and predicate structure unchanged
SELECT *
FROM ((( title t LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id) RIGHT OUTER JOIN name n ON ci.person_id = n.id) FULL OUTER JOIN (( movie_companies mc INNER JOIN company_name cn ON mc.company_id = cn.id) LEFT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE cn.id BETWEEN 50 AND 5000;
