-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 21a
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT mc.company_id, cn.id, t.id, mc.movie_id, mc.company_type_id, ct.id, mi.movie_id
FROM (company_name cn INNER JOIN (movie_info mi FULL OUTER JOIN (title t RIGHT OUTER JOIN (company_type ct LEFT OUTER JOIN movie_companies mc ON mc.company_type_id = ct.id) ON t.id = mc.movie_id) ON mi.movie_id = t.id) ON mc.company_id = cn.id)
WHERE t.production_year BETWEEN 1950 AND 2006;
