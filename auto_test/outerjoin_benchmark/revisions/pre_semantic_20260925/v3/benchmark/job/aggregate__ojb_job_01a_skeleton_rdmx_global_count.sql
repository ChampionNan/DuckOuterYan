-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=mc.movie_id; group_key=ct.id
SELECT COUNT(*) AS row_count
FROM (title t LEFT OUTER JOIN (info_type it INNER JOIN (movie_info_idx mi_idx FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_type ct ON ct.id = mc.company_type_id) ON mc.movie_id = mi_idx.movie_id) ON it.id = mi_idx.info_type_id) ON t.id = mc.movie_id)
WHERE ct.id % 1000 = 0;
