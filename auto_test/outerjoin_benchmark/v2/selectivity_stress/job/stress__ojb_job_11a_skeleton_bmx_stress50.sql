-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; cross-product-free bushy FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress50; approximately 50% of hash buckets; anchor=cn.id; predicate=hash(cn.id) % 4000 < 2000
SELECT *
FROM ((company_name cn FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) FULL OUTER JOIN (movie_keyword mk FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) ON mk.movie_id = mc.movie_id)
WHERE hash(cn.id) % 4000 < 2000;
