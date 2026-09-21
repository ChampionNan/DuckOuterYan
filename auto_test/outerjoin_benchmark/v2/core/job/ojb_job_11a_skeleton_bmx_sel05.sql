-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; cross-product-free bushy FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=mc.company_id; predicate=hash(anchor) % 20 = 0
SELECT *
FROM ((company_name cn FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) FULL OUTER JOIN (movie_keyword mk FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) ON mk.movie_id = mc.movie_id)
WHERE (cn.id % 1000 = 0)
  AND hash(mc.company_id) % 20 = 0;
