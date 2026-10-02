-- query_type: join; family: job
-- source: SQLStorm v1.0/job/queries/11914.sql
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((aka_name a FULL OUTER JOIN (cast_info ci FULL OUTER JOIN role_type r ON ci.role_id = r.id) ON a.person_id = ci.person_id) INNER JOIN (title t LEFT OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_type c ON mc.company_type_id = c.id) ON t.id = mc.movie_id) ON ci.movie_id = t.id)
WHERE t.production_year >= 2013;
