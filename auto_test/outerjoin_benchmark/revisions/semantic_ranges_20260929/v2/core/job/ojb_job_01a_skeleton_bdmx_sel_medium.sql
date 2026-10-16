-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: JOB 01a ranking and audience-metric categories
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: job_info_category; tier=medium; JOB 01a ranking and audience-metric categories
-- predicate: it.info IN ('top 250 rank', 'votes')
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((movie_companies mc INNER JOIN company_type ct ON ct.id = mc.company_type_id) LEFT OUTER JOIN title t ON t.id = mc.movie_id) RIGHT OUTER JOIN (info_type it FULL OUTER JOIN movie_info_idx mi_idx ON it.id = mi_idx.info_type_id) ON t.id = mi_idx.movie_id)
WHERE it.info IN ('top 250 rank', 'votes');
