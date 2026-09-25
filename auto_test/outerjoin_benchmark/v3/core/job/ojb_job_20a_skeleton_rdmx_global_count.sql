-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 20a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=cc.subject_id; group_key=cct1.id
SELECT COUNT(*) AS row_count
FROM (char_name chn LEFT OUTER JOIN (cast_info ci INNER JOIN (comp_cast_type cct2 FULL OUTER JOIN (comp_cast_type cct1 RIGHT OUTER JOIN complete_cast cc ON cct1.id = cc.subject_id) ON cct2.id = cc.status_id) ON ci.movie_id = cc.movie_id) ON chn.id = ci.role_id)
WHERE cc.id % 1000 = 0;
