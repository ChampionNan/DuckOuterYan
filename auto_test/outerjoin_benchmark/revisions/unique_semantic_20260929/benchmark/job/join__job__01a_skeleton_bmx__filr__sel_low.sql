-- query_type: join; family: job
-- source: JOB 01a
-- semantic_filter: job_info_category; tier=low; JOB 01a ranking and audience-metric categories
-- predicate: it.info = 'top 250 rank'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((company_type ct FULL OUTER JOIN movie_companies mc ON ct.id = mc.company_type_id) INNER JOIN (title t LEFT OUTER JOIN (movie_info_idx mi_idx RIGHT OUTER JOIN info_type it ON it.id = mi_idx.info_type_id) ON t.id = mi_idx.movie_id) ON t.id = mc.movie_id)
WHERE it.info = 'top 250 rank';
