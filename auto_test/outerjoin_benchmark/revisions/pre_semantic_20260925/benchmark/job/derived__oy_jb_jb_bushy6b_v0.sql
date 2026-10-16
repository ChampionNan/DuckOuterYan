-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFILR; relation and predicate structure unchanged
SELECT *
FROM (((( title t RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) INNER JOIN ( movie_info mi LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) RIGHT OUTER JOIN kind_type kt ON t.kind_id = kt.id)
WHERE k.id BETWEEN 50 AND 5000;
