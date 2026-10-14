-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 21a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT mc.company_id, cn.id, t.id, mc.movie_id, mc.company_type_id, ct.id, mi.movie_id
FROM ((movie_info mi LEFT OUTER JOIN title t ON mi.movie_id = t.id) INNER JOIN (company_name cn FULL OUTER JOIN (company_type ct RIGHT OUTER JOIN movie_companies mc ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE t.production_year BETWEEN 1950 AND 2000;
