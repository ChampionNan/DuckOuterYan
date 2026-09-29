-- source: JOB 30a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 30a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=cc.subject_id; group_key=cct1.id
SELECT cct1.id AS group_key, SUM(cc.subject_id) AS key_sum
FROM (movie_info mi LEFT OUTER JOIN (cast_info ci INNER JOIN (comp_cast_type cct2 FULL OUTER JOIN (comp_cast_type cct1 RIGHT OUTER JOIN complete_cast cc ON cct1.id = cc.subject_id) ON cct2.id = cc.status_id) ON ci.movie_id = cc.movie_id) ON ci.movie_id = mi.movie_id)
WHERE cc.id % 1000 = 0
GROUP BY cct1.id;
