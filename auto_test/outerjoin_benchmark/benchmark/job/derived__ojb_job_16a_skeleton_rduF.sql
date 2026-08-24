-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 16a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (aka_name an FULL OUTER JOIN (company_name cn FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN (cast_info ci FULL OUTER JOIN movie_keyword mk ON ci.movie_id = mk.movie_id) ON ci.movie_id = mc.movie_id) ON mc.company_id = cn.id) ON an.person_id = ci.person_id)
WHERE an.id % 1000 = 0;
