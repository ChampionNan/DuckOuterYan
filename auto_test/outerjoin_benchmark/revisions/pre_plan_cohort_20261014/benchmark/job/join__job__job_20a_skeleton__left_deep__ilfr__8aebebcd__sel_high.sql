-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 20a
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id, cc.movie_id, cct1.id, cc.subject_id, cct2.id, cc.status_id, ci.movie_id
FROM ((((complete_cast cc INNER JOIN title t ON t.id = cc.movie_id) LEFT OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) FULL OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id)
WHERE t.production_year >= 2001;
