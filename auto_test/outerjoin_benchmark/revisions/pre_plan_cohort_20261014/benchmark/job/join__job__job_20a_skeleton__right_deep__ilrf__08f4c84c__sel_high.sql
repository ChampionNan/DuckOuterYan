-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 20a
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id, cc.movie_id, cct1.id, cc.subject_id, cct2.id, cc.status_id, ci.movie_id
FROM (comp_cast_type cct1 INNER JOIN (comp_cast_type cct2 LEFT OUTER JOIN (complete_cast cc RIGHT OUTER JOIN (cast_info ci FULL OUTER JOIN title t ON t.id = ci.movie_id) ON t.id = cc.movie_id) ON cct2.id = cc.status_id) ON cct1.id = cc.subject_id)
WHERE t.production_year >= 2001;
