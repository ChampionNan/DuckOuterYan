-- source: JOB 30a
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 30a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((movie_info mi FULL OUTER JOIN cast_info ci ON ci.movie_id = mi.movie_id) FULL OUTER JOIN ((comp_cast_type cct1 FULL OUTER JOIN complete_cast cc ON cct1.id = cc.subject_id) FULL OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) ON ci.movie_id = cc.movie_id)
WHERE cc.id % 1000 = 0;
