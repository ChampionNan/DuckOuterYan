-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=mk.movie_id; predicate=hash(anchor) % 100 = 0
SELECT *
FROM (title t FULL OUTER JOIN (name n FULL OUTER JOIN (keyword k FULL OUTER JOIN (movie_keyword mk FULL OUTER JOIN cast_info ci ON ci.movie_id = mk.movie_id) ON k.id = mk.keyword_id) ON n.id = ci.person_id) ON t.id = mk.movie_id)
WHERE (ci.id % 1000 = 0)
  AND hash(mk.movie_id) % 100 = 0;
