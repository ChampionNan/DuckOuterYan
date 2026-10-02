-- query_type: join; family: job
-- source: JOB 06a
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (keyword k FULL OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN (title t LEFT OUTER JOIN (cast_info ci INNER JOIN name n ON n.id = ci.person_id) ON t.id = ci.movie_id) ON t.id = mk.movie_id) ON k.id = mk.keyword_id)
WHERE t.production_year >= 2001;
