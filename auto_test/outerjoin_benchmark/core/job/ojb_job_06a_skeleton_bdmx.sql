-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (((keyword k FULL OUTER JOIN movie_keyword mk ON k.id = mk.keyword_id) FULL OUTER JOIN title t ON t.id = mk.movie_id) FULL OUTER JOIN (name n FULL OUTER JOIN cast_info ci ON n.id = ci.person_id) ON ci.movie_id = mk.movie_id)
WHERE ci.id % 1000 = 0;
