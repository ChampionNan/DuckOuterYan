-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((((title t FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON k.id = mk.keyword_id) FULL OUTER JOIN cast_info ci ON ci.movie_id = mk.movie_id) FULL OUTER JOIN name n ON n.id = ci.person_id)
WHERE ci.id % 1000 = 0;
