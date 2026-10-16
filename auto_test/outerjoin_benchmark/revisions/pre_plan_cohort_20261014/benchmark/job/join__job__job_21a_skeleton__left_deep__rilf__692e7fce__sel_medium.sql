-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 21a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT mc.company_id, cn.id, t.id, mc.movie_id, mc.company_type_id, ct.id, mi.movie_id
FROM ((((movie_companies mc RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) INNER JOIN title t ON t.id = mc.movie_id) LEFT OUTER JOIN movie_info mi ON mi.movie_id = t.id) FULL OUTER JOIN company_name cn ON mc.company_id = cn.id)
WHERE t.production_year BETWEEN 1950 AND 2000;
