-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRFI; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRFI; relation and predicate structure unchanged
SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    INNER JOIN company_name cn ON mc.company_id = cn.id
WHERE ci.person_id >= 100 AND ci.person_id <= 9000;
