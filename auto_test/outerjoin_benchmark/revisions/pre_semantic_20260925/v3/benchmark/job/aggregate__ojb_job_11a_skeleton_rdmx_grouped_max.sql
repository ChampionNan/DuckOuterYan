-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=mc.company_id; group_key=cn.id
SELECT cn.id AS group_key, MAX(mc.company_id) AS max_key
FROM (keyword k LEFT OUTER JOIN (movie_keyword mk INNER JOIN (company_type ct FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON mc.company_type_id = ct.id) ON mk.movie_id = mc.movie_id) ON mk.keyword_id = k.id)
WHERE cn.id % 1000 = 0
GROUP BY cn.id;
