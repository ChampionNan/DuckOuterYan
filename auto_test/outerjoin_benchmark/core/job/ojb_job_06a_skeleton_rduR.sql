-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (name n FULL OUTER JOIN (cast_info ci FULL OUTER JOIN (keyword k FULL OUTER JOIN (movie_keyword mk FULL OUTER JOIN title t ON t.id = mk.movie_id) ON k.id = mk.keyword_id) ON ci.movie_id = mk.movie_id) ON n.id = ci.person_id)
WHERE ci.id % 1000 = 0;
