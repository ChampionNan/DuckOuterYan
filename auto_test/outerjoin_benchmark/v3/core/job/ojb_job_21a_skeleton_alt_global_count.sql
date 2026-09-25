-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=mc.movie_id; group_key=mc.company_id
SELECT COUNT(*) AS row_count
FROM ((((company_name cn FULL OUTER JOIN movie_companies mc ON mc.company_id = cn.id) INNER JOIN company_type ct ON mc.company_type_id = ct.id) LEFT OUTER JOIN movie_info mi ON mc.movie_id = mi.movie_id) RIGHT OUTER JOIN movie_keyword mk ON mk.movie_id = mc.movie_id)
WHERE cn.id % 1000 = 0;
