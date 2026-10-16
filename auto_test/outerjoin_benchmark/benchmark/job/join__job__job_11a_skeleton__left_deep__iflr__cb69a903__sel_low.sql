-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 11a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT mc.company_id, cn.id, t.id, mc.movie_id, mc.company_type_id, ct.id, mk.movie_id
FROM ((((company_name cn INNER JOIN movie_companies mc ON mc.company_id = cn.id) FULL OUTER JOIN title t ON t.id = mc.movie_id) LEFT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id)
WHERE t.production_year BETWEEN 1999 AND 2000;
