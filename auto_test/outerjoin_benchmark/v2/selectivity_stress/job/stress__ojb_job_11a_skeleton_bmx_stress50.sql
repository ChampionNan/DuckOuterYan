-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress50; approximately 50% of hash buckets; anchor=mc.company_id; predicate=hash(mc.company_id) % 4000 < 2000
SELECT *
FROM ((company_name cn FULL OUTER JOIN (movie_companies mc INNER JOIN company_type ct ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) LEFT OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON mk.movie_id = mc.movie_id)
WHERE (cn.id % 1000 = 0)
  AND hash(mc.company_id) % 4000 < 2000;
