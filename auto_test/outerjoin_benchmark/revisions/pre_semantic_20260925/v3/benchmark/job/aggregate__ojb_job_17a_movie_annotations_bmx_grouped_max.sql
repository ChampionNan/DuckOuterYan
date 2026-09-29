-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=mk.movie_id; group_key=t.id
SELECT t.id AS group_key, MAX(mk.movie_id) AS max_key
FROM ((title t INNER JOIN (movie_keyword mk LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id) RIGHT OUTER JOIN (cast_info ci FULL OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id)
WHERE t.id % 1000 = 0
GROUP BY t.id;
