-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRFI; relation and predicate structure unchanged
SELECT *
FROM (((( title t INNER JOIN movie_keyword mk ON t.id = mk.movie_id) LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id) RIGHT OUTER JOIN ( movie_info mi FULL OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) INNER JOIN kind_type kt ON t.kind_id = kt.id)
WHERE k.id % 2 = 1;
