-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=mc.company_id; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM (keyword k LEFT OUTER JOIN (movie_keyword mk INNER JOIN (company_type ct FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON mc.company_type_id = ct.id) ON mk.movie_id = mc.movie_id) ON mk.keyword_id = k.id)
WHERE (cn.id % 1000 = 0)
  AND hash(mc.company_id) % 1000 = 0;
