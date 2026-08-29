-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((keyword k FULL OUTER JOIN movie_keyword mk ON mk.keyword_id = k.id) FULL OUTER JOIN ((movie_companies mc FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON mk.movie_id = mc.movie_id)
WHERE cn.id % 1000 = 0;
