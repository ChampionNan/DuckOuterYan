-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=mc.movie_id; group_key=ct.id
SELECT ct.id AS group_key, SUM(mc.movie_id) AS key_sum
FROM ((company_type ct FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN title t ON t.id = mc.movie_id) ON ct.id = mc.company_type_id) INNER JOIN (movie_info_idx mi_idx LEFT OUTER JOIN info_type it ON it.id = mi_idx.info_type_id) ON mc.movie_id = mi_idx.movie_id)
WHERE ct.id % 1000 = 0
GROUP BY ct.id;
