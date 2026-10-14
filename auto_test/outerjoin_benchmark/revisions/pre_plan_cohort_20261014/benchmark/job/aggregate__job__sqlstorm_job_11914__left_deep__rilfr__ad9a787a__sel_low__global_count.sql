-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/11914.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM (((((cast_info ci RIGHT OUTER JOIN role_type r ON ci.role_id = r.id) INNER JOIN title t ON ci.movie_id = t.id) LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id) FULL OUTER JOIN company_type c ON mc.company_type_id = c.id) RIGHT OUTER JOIN aka_name a ON a.person_id = ci.person_id)
WHERE t.production_year >= 2013;
