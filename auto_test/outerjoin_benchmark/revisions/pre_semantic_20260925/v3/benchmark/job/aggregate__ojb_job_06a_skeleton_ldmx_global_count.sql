-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=mk.movie_id; group_key=ci.movie_id
SELECT COUNT(*) AS row_count
FROM ((((cast_info ci LEFT OUTER JOIN movie_keyword mk ON ci.movie_id = mk.movie_id) RIGHT OUTER JOIN keyword k ON k.id = mk.keyword_id) FULL OUTER JOIN name n ON n.id = ci.person_id) INNER JOIN title t ON t.id = mk.movie_id)
WHERE ci.id % 1000 = 0;
