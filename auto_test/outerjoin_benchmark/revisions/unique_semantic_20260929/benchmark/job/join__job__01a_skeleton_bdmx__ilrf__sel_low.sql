-- query_type: join; family: job
-- source: JOB 01a
-- semantic_filter: job_info_category; tier=low; JOB 01a ranking and audience-metric categories
-- predicate: it.info = 'top 250 rank'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((movie_companies mc INNER JOIN company_type ct ON ct.id = mc.company_type_id) LEFT OUTER JOIN title t ON t.id = mc.movie_id) RIGHT OUTER JOIN (info_type it FULL OUTER JOIN movie_info_idx mi_idx ON it.id = mi_idx.info_type_id) ON t.id = mi_idx.movie_id)
WHERE it.info = 'top 250 rank';
