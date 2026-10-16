-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 21a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM ((movie_info mi FULL OUTER JOIN title t ON mi.movie_id = t.id) RIGHT OUTER JOIN (company_name cn LEFT OUTER JOIN (company_type ct INNER JOIN movie_companies mc ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE t.production_year BETWEEN 1999 AND 2000;
