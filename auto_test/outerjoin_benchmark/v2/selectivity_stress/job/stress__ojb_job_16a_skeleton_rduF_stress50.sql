-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 16a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress50; approximately 50% of hash buckets; anchor=ci.movie_id; predicate=hash(ci.movie_id) % 4000 < 2000
SELECT *
FROM (aka_name an LEFT OUTER JOIN (company_name cn FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN (cast_info ci INNER JOIN movie_keyword mk ON ci.movie_id = mk.movie_id) ON ci.movie_id = mc.movie_id) ON mc.company_id = cn.id) ON an.person_id = ci.person_id)
WHERE (an.id % 1000 = 0)
  AND hash(ci.movie_id) % 4000 < 2000;
