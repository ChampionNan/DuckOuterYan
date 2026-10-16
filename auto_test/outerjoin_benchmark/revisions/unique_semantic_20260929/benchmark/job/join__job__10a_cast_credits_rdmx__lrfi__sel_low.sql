-- query_type: join; family: job
-- source: JOB 10a
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS title_id, t.title, ci.person_id, cn.name AS company_name, rt.role, mc.company_id
FROM (company_name cn INNER JOIN (movie_companies mc FULL OUTER JOIN (role_type rt RIGHT OUTER JOIN (cast_info ci LEFT OUTER JOIN title t ON t.id = ci.movie_id) ON rt.id = ci.role_id) ON t.id = mc.movie_id) ON cn.id = mc.company_id)
WHERE t.production_year >= 2013;
