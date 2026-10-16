-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=mc.movie_id; group_key=mc.company_id
SELECT COUNT(*) AS row_count
FROM (movie_keyword mk LEFT OUTER JOIN (movie_info mi INNER JOIN (company_type ct FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON mc.company_type_id = ct.id) ON mc.movie_id = mi.movie_id) ON mk.movie_id = mc.movie_id)
WHERE cn.id % 1000 = 0;
