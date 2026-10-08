-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 01a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ct.id, mc.company_type_id, t.id, mc.movie_id, mi_idx.movie_id, it.id, mi_idx.info_type_id
FROM (info_type it LEFT OUTER JOIN (movie_info_idx mi_idx RIGHT OUTER JOIN (title t INNER JOIN (movie_companies mc FULL OUTER JOIN company_type ct ON ct.id = mc.company_type_id) ON t.id = mc.movie_id) ON t.id = mi_idx.movie_id) ON it.id = mi_idx.info_type_id)
WHERE t.production_year >= 2013;
