-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress10; approximately 10% of hash buckets; anchor=cn.id; predicate=hash(cn.id) % 4000 < 400
SELECT *
FROM ((((company_name cn FULL OUTER JOIN movie_companies mc ON mc.company_id = cn.id) FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) FULL OUTER JOIN movie_info mi ON mc.movie_id = mi.movie_id) FULL OUTER JOIN movie_keyword mk ON mk.movie_id = mc.movie_id)
WHERE hash(cn.id) % 4000 < 400;
