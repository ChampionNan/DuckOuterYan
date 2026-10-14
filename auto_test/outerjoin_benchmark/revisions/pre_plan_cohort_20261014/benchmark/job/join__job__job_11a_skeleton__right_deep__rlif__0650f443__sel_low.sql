-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 11a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT mc.company_id, cn.id, t.id, mc.movie_id, mc.company_type_id, ct.id, mk.movie_id
FROM (movie_keyword mk RIGHT OUTER JOIN (company_type ct LEFT OUTER JOIN (title t INNER JOIN (movie_companies mc FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON mc.company_type_id = ct.id) ON t.id = mk.movie_id)
WHERE t.production_year BETWEEN 1999 AND 2000;
