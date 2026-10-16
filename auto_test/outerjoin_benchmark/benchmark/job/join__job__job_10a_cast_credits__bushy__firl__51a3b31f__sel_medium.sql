-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 10a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id AS title_id, t.title, ci.person_id, cn.name AS company_name, rt.role, mc.company_id
FROM ((role_type rt FULL OUTER JOIN cast_info ci ON rt.id = ci.role_id) INNER JOIN (title t RIGHT OUTER JOIN (company_name cn LEFT OUTER JOIN movie_companies mc ON cn.id = mc.company_id) ON t.id = mc.movie_id) ON t.id = ci.movie_id)
WHERE t.production_year >= 2008;
