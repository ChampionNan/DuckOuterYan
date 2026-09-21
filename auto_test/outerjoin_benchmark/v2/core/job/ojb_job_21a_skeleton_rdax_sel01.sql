-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=mc.movie_id; predicate=hash(anchor) % 100 = 0
SELECT *
FROM (movie_keyword mk FULL OUTER JOIN (movie_info mi FULL OUTER JOIN (company_name cn FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) ON mc.movie_id = mi.movie_id) ON mk.movie_id = mc.movie_id)
WHERE (cn.id % 1000 = 0)
  AND hash(mc.movie_id) % 100 = 0;
