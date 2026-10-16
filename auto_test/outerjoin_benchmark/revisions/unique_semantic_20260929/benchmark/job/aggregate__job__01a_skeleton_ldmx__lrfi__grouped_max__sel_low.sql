-- query_type: aggregate; family: job
-- source: JOB 01a
-- semantic_filter: job_info_category; tier=low; JOB 01a ranking and audience-metric categories
-- predicate: it.info = 'top 250 rank'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT ct.id AS group_key, MAX(mi_idx.movie_id) AS max_key
FROM ((((company_type ct LEFT OUTER JOIN movie_companies mc ON ct.id = mc.company_type_id) RIGHT OUTER JOIN title t ON t.id = mc.movie_id) FULL OUTER JOIN movie_info_idx mi_idx ON t.id = mi_idx.movie_id) INNER JOIN info_type it ON it.id = mi_idx.info_type_id)
WHERE it.info = 'top 250 rank'
GROUP BY ct.id;
