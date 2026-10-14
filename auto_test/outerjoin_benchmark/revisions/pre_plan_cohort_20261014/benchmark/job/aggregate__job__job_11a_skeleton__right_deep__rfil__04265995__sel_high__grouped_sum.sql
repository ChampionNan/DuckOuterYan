-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 11a
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT cn.id AS group_key, SUM(mc.company_id) AS key_sum
FROM (movie_keyword mk RIGHT OUTER JOIN (company_type ct FULL OUTER JOIN (title t INNER JOIN (movie_companies mc LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON mc.company_type_id = ct.id) ON t.id = mk.movie_id)
WHERE t.production_year BETWEEN 1950 AND 2006
GROUP BY cn.id;
