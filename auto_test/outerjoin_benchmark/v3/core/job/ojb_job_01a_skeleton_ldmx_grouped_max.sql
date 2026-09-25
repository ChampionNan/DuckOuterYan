-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=mc.movie_id; group_key=ct.id
SELECT ct.id AS group_key, MAX(mc.movie_id) AS max_key
FROM ((((company_type ct LEFT OUTER JOIN movie_companies mc ON ct.id = mc.company_type_id) RIGHT OUTER JOIN movie_info_idx mi_idx ON mc.movie_id = mi_idx.movie_id) FULL OUTER JOIN info_type it ON it.id = mi_idx.info_type_id) INNER JOIN title t ON t.id = mc.movie_id)
WHERE ct.id % 1000 = 0
GROUP BY ct.id;
