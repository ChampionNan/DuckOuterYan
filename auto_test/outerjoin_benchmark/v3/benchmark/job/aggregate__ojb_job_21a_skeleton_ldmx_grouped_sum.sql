-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=mc.movie_id; group_key=mc.company_id
SELECT mc.company_id AS group_key, SUM(mc.movie_id) AS key_sum
FROM ((((company_name cn LEFT OUTER JOIN movie_companies mc ON mc.company_id = cn.id) RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) FULL OUTER JOIN movie_info mi ON mc.movie_id = mi.movie_id) INNER JOIN movie_keyword mk ON mk.movie_id = mc.movie_id)
WHERE cn.id % 1000 = 0
GROUP BY mc.company_id;
