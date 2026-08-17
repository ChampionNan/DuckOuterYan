-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; uniform left-deep LEFT OUTER JOIN control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((((cast_info ci LEFT OUTER JOIN movie_keyword mk ON ci.movie_id = mk.movie_id) LEFT OUTER JOIN keyword k ON k.id = mk.keyword_id) LEFT OUTER JOIN name n ON n.id = ci.person_id) LEFT OUTER JOIN title t ON t.id = mk.movie_id)
WHERE ci.id % 1000 = 0;
