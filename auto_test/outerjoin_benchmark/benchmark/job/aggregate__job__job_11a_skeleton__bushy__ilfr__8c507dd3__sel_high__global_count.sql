-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 11a
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM ((movie_keyword mk INNER JOIN title t ON t.id = mk.movie_id) LEFT OUTER JOIN (company_name cn FULL OUTER JOIN (company_type ct RIGHT OUTER JOIN movie_companies mc ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE t.production_year BETWEEN 1950 AND 2006;
