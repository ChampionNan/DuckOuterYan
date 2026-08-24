-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 16a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((((movie_keyword mk FULL OUTER JOIN cast_info ci ON ci.movie_id = mk.movie_id) FULL OUTER JOIN movie_companies mc ON ci.movie_id = mc.movie_id) FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) FULL OUTER JOIN aka_name an ON an.person_id = ci.person_id)
WHERE an.id % 1000 = 0;
