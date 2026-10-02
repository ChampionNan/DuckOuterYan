-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 10a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id AS title_id, t.title, ci.person_id, cn.name AS company_name, rt.role, mc.company_id
FROM (company_name cn LEFT OUTER JOIN (movie_companies mc RIGHT OUTER JOIN (role_type rt INNER JOIN (cast_info ci FULL OUTER JOIN title t ON t.id = ci.movie_id) ON rt.id = ci.role_id) ON t.id = mc.movie_id) ON cn.id = mc.company_id)
WHERE t.production_year >= 2008;
