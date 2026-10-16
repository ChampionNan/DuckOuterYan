-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM (company_name cn LEFT OUTER JOIN (company_type ct RIGHT OUTER JOIN (movie_info mi FULL OUTER JOIN (movie_companies mc INNER JOIN movie_keyword mk ON mk.movie_id = mc.movie_id) ON mc.movie_id = mi.movie_id) ON mc.company_type_id = ct.id) ON mc.company_id = cn.id)
WHERE cn.id % 1000 = 0;
