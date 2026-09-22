-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFIL; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFIL; relation and predicate structure unchanged
SELECT *
FROM title t
    RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    FULL OUTER JOIN keyword k ON mk.keyword_id = k.id
    INNER JOIN movie_info mi ON t.id = mi.movie_id
    LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE mk.keyword_id < 200;
