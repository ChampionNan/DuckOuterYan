-- source: JOB 26a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 26a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=cc.subject_id; group_key=cct1.id
SELECT cct1.id AS group_key, SUM(cc.subject_id) AS key_sum
FROM ((((complete_cast cc LEFT OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) RIGHT OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) FULL OUTER JOIN cast_info ci ON ci.movie_id = cc.movie_id) INNER JOIN char_name chn ON chn.id = ci.role_id)
WHERE cc.id % 1000 = 0
GROUP BY cct1.id;
