-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FILR; relation and predicate structure unchanged
SELECT *
FROM title t
    FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id
    INNER JOIN role_type rt ON ci.role_id = rt.id
    LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE mk.movie_id > 100;
