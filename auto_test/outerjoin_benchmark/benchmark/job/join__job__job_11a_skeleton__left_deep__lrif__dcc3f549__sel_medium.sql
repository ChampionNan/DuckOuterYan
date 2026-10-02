-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 11a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT mc.company_id, cn.id, t.id, mc.movie_id, mc.company_type_id, ct.id, mk.movie_id
FROM ((((company_name cn LEFT OUTER JOIN movie_companies mc ON mc.company_id = cn.id) RIGHT OUTER JOIN title t ON t.id = mc.movie_id) INNER JOIN company_type ct ON mc.company_type_id = ct.id) FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id)
WHERE t.production_year BETWEEN 1950 AND 2000;
