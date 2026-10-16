-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRFI; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRFI; relation graph retained; semantic filter replaced
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((( title t INNER JOIN movie_keyword mk ON t.id = mk.movie_id) LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id) RIGHT OUTER JOIN ( movie_info mi FULL OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) INNER JOIN kind_type kt ON t.kind_id = kt.id)
WHERE t.production_year >= 2013;
