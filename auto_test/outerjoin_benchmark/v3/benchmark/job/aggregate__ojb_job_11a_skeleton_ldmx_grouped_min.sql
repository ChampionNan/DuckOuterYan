-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=mc.company_id; group_key=cn.id
SELECT cn.id AS group_key, MIN(mc.company_id) AS min_key
FROM ((((company_name cn LEFT OUTER JOIN movie_companies mc ON mc.company_id = cn.id) RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) FULL OUTER JOIN movie_keyword mk ON mk.movie_id = mc.movie_id) INNER JOIN keyword k ON mk.keyword_id = k.id)
WHERE cn.id % 1000 = 0
GROUP BY cn.id;
