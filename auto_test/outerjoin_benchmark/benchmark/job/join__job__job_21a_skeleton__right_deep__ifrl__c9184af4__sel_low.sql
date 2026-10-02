-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 21a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT mc.company_id, cn.id, t.id, mc.movie_id, mc.company_type_id, ct.id, mi.movie_id
FROM (movie_info mi INNER JOIN (company_type ct FULL OUTER JOIN (title t RIGHT OUTER JOIN (movie_companies mc LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON mc.company_type_id = ct.id) ON mi.movie_id = t.id)
WHERE t.production_year BETWEEN 1999 AND 2000;
