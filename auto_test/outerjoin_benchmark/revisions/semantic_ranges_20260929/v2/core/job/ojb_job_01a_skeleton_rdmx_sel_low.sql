-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: JOB 01a ranking and audience-metric categories
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: job_info_category; tier=low; JOB 01a ranking and audience-metric categories
-- predicate: it.info = 'top 250 rank'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (info_type it LEFT OUTER JOIN (movie_info_idx mi_idx INNER JOIN (title t FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_type ct ON ct.id = mc.company_type_id) ON t.id = mc.movie_id) ON t.id = mi_idx.movie_id) ON it.id = mi_idx.info_type_id)
WHERE it.info = 'top 250 rank';
