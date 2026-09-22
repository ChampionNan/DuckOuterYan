-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRFIL; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FILRF; relation and predicate structure unchanged
SELECT *
FROM (((( title t LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id) FULL OUTER JOIN ( movie_info mi INNER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) LEFT OUTER JOIN kind_type kt ON t.kind_id = kt.id)
WHERE k.id BETWEEN 50 AND 5000;
