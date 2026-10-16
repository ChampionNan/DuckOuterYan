-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation graph retained; semantic filter replaced
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (( title t RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id) FULL OUTER JOIN ( movie_companies mc INNER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE t.production_year >= 2013;
