-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation and predicate structure unchanged
SELECT *
FROM title t
    INNER JOIN cast_info ci ON t.id = ci.movie_id
    LEFT OUTER JOIN role_type rt ON ci.role_id = rt.id
    RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    FULL OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE mk.movie_id > 100;
