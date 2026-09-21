-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 16a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress02; approximately 0.2% of hash buckets; anchor=an.id; predicate=hash(an.id) % 4000 < 8
SELECT *
FROM (aka_name an FULL OUTER JOIN (company_name cn FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN (cast_info ci FULL OUTER JOIN movie_keyword mk ON ci.movie_id = mk.movie_id) ON ci.movie_id = mc.movie_id) ON mc.company_id = cn.id) ON an.person_id = ci.person_id)
WHERE hash(an.id) % 4000 < 8;
