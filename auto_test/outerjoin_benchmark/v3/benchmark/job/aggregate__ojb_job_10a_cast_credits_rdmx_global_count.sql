-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ci.role_id; group_key=t.id
SELECT COUNT(*) AS row_count
FROM (movie_companies mc INNER JOIN (role_type rt FULL OUTER JOIN (char_name chn RIGHT OUTER JOIN (cast_info ci LEFT OUTER JOIN title t ON t.id = ci.movie_id) ON chn.id = ci.role_id) ON rt.id = ci.role_id) ON t.id = mc.movie_id)
WHERE t.production_year > 2005;
