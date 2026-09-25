-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FILR; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FILR; relation and predicate structure unchanged
SELECT *
FROM title t
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    INNER JOIN keyword k ON mk.keyword_id = k.id
    LEFT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE mk.keyword_id < 200;
