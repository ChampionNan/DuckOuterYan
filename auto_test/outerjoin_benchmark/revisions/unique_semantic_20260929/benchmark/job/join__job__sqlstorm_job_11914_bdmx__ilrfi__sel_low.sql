-- query_type: join; family: job
-- source: SQLStorm v1.0/job/queries/11914.sql
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((cast_info ci INNER JOIN aka_name a ON a.person_id = ci.person_id) INNER JOIN role_type r ON ci.role_id = r.id) LEFT OUTER JOIN title t ON ci.movie_id = t.id) RIGHT OUTER JOIN (company_type c FULL OUTER JOIN movie_companies mc ON mc.company_type_id = c.id) ON t.id = mc.movie_id)
WHERE t.production_year >= 2013;
