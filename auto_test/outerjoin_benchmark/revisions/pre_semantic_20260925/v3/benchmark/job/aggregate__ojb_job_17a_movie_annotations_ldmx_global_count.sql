-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=mk.movie_id; group_key=t.id
SELECT COUNT(*) AS row_count
FROM ((((title t INNER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON mk.keyword_id = k.id)
WHERE t.id % 1000 = 0;
