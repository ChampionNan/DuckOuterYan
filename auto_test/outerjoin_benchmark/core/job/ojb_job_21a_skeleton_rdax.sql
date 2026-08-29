-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (movie_keyword mk FULL OUTER JOIN (movie_info mi FULL OUTER JOIN (company_name cn FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) ON mc.movie_id = mi.movie_id) ON mk.movie_id = mc.movie_id)
WHERE cn.id % 1000 = 0;
