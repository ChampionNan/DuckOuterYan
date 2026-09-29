-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=ci.role_id; group_key=t.id
SELECT t.id AS group_key, SUM(ci.role_id) AS key_sum
FROM ((title t LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id) RIGHT OUTER JOIN ((cast_info ci INNER JOIN role_type rt ON rt.id = ci.role_id) FULL OUTER JOIN char_name chn ON chn.id = ci.role_id) ON t.id = ci.movie_id)
WHERE t.production_year > 2005
GROUP BY t.id;
