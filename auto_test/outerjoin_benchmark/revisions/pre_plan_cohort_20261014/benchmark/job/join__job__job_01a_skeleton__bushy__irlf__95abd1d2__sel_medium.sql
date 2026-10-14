-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 01a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ct.id, mc.company_type_id, t.id, mc.movie_id, mi_idx.movie_id, it.id, mi_idx.info_type_id
FROM ((company_type ct INNER JOIN movie_companies mc ON ct.id = mc.company_type_id) RIGHT OUTER JOIN (info_type it LEFT OUTER JOIN (movie_info_idx mi_idx FULL OUTER JOIN title t ON t.id = mi_idx.movie_id) ON it.id = mi_idx.info_type_id) ON t.id = mc.movie_id)
WHERE t.production_year >= 2008;
