-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRFI; relation and predicate structure unchanged
SELECT *
FROM ((( title t INNER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN (( movie_companies mc FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) INNER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE cn.id BETWEEN 50 AND 5000;
