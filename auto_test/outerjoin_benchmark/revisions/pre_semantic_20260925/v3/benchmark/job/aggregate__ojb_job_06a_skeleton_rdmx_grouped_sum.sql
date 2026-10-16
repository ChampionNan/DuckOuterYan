-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=mk.movie_id; group_key=ci.movie_id
SELECT ci.movie_id AS group_key, SUM(mk.movie_id) AS key_sum
FROM (title t LEFT OUTER JOIN (name n INNER JOIN (keyword k FULL OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN cast_info ci ON ci.movie_id = mk.movie_id) ON k.id = mk.keyword_id) ON n.id = ci.person_id) ON t.id = mk.movie_id)
WHERE ci.id % 1000 = 0
GROUP BY ci.movie_id;
