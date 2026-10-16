-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 01a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ct.id, mc.company_type_id, t.id, mc.movie_id, mi_idx.movie_id, it.id, mi_idx.info_type_id
FROM (((movie_info_idx mi_idx RIGHT OUTER JOIN info_type it ON it.id = mi_idx.info_type_id) INNER JOIN title t ON t.id = mi_idx.movie_id) LEFT OUTER JOIN (company_type ct FULL OUTER JOIN movie_companies mc ON ct.id = mc.company_type_id) ON t.id = mc.movie_id)
WHERE t.production_year >= 2008;
