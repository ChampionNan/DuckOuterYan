-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=mc.company_id; group_key=cn.id
SELECT COUNT(*) AS row_count
FROM ((company_name cn FULL OUTER JOIN (movie_companies mc INNER JOIN company_type ct ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) LEFT OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON mk.movie_id = mc.movie_id)
WHERE cn.id % 1000 = 0;
