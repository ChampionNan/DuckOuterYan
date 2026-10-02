-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/11914.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM (role_type r RIGHT OUTER JOIN (company_type c FULL OUTER JOIN (movie_companies mc LEFT OUTER JOIN (title t INNER JOIN (cast_info ci RIGHT OUTER JOIN aka_name a ON a.person_id = ci.person_id) ON ci.movie_id = t.id) ON t.id = mc.movie_id) ON mc.company_type_id = c.id) ON ci.role_id = r.id)
WHERE t.production_year >= 2013;
