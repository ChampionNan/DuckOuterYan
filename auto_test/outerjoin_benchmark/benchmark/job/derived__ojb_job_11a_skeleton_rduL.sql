-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (company_name cn FULL OUTER JOIN (company_type ct FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN (movie_keyword mk FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) ON mk.movie_id = mc.movie_id) ON mc.company_type_id = ct.id) ON mc.company_id = cn.id)
WHERE cn.id % 1000 = 0;
