-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: JOB 01a ranking and audience-metric categories
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=mi_idx.movie_id; group_key=ct.id
-- semantic_filter: job_info_category; tier=low; JOB 01a ranking and audience-metric categories
-- predicate: it.info = 'top 250 rank'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT ct.id AS group_key, SUM(mi_idx.movie_id) AS key_sum
FROM ((company_type ct FULL OUTER JOIN movie_companies mc ON ct.id = mc.company_type_id) INNER JOIN (title t LEFT OUTER JOIN (movie_info_idx mi_idx RIGHT OUTER JOIN info_type it ON it.id = mi_idx.info_type_id) ON t.id = mi_idx.movie_id) ON t.id = mc.movie_id)
WHERE it.info = 'top 250 rank'
GROUP BY ct.id;
