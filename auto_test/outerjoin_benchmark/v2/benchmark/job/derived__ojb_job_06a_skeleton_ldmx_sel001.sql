-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=mk.movie_id; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM ((((cast_info ci FULL OUTER JOIN movie_keyword mk ON ci.movie_id = mk.movie_id) FULL OUTER JOIN keyword k ON k.id = mk.keyword_id) FULL OUTER JOIN name n ON n.id = ci.person_id) FULL OUTER JOIN title t ON t.id = mk.movie_id)
WHERE (ci.id % 1000 = 0)
  AND hash(mk.movie_id) % 1000 = 0;
