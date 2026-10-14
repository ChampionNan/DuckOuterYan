-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 20a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id AS group_key, MAX(cc.movie_id) AS max_key
FROM (cast_info ci LEFT OUTER JOIN (comp_cast_type cct2 INNER JOIN (comp_cast_type cct1 RIGHT OUTER JOIN (title t FULL OUTER JOIN complete_cast cc ON t.id = cc.movie_id) ON cct1.id = cc.subject_id) ON cct2.id = cc.status_id) ON t.id = ci.movie_id)
WHERE t.production_year >= 2013
GROUP BY t.id;
