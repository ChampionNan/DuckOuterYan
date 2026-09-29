-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=mk.movie_id; group_key=t.id
SELECT t.id AS group_key, MIN(mk.movie_id) AS min_key
FROM (keyword k INNER JOIN (movie_keyword mk FULL OUTER JOIN (name n RIGHT OUTER JOIN (cast_info ci LEFT OUTER JOIN title t ON t.id = ci.movie_id) ON ci.person_id = n.id) ON t.id = mk.movie_id) ON mk.keyword_id = k.id)
WHERE t.id % 1000 = 0
GROUP BY t.id;
