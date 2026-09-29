-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFIL; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFIL; relation and predicate structure unchanged
SELECT *
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN name n ON ci.person_id = n.id
    INNER JOIN movie_companies mc ON t.id = mc.movie_id
    LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE ci.person_id >= 100 AND ci.person_id <= 9000;
