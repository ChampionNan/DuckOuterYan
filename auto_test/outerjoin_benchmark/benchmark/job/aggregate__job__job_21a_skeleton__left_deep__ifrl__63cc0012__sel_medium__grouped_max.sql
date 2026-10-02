-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 21a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT cn.id AS group_key, MAX(mc.company_id) AS max_key
FROM ((((movie_companies mc INNER JOIN company_type ct ON mc.company_type_id = ct.id) FULL OUTER JOIN title t ON t.id = mc.movie_id) RIGHT OUTER JOIN movie_info mi ON mi.movie_id = t.id) LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id)
WHERE t.production_year BETWEEN 1950 AND 2000
GROUP BY cn.id;
