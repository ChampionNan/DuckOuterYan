-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; cross-product-free bushy FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((cast_info ci FULL OUTER JOIN name n ON n.id = ci.person_id) FULL OUTER JOIN ((movie_keyword mk FULL OUTER JOIN title t ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON k.id = mk.keyword_id) ON ci.movie_id = mk.movie_id)
WHERE ci.id % 1000 = 0;
