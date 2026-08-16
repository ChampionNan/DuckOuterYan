-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 16a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (movie_keyword mk FULL OUTER JOIN (company_name cn RIGHT OUTER JOIN (movie_companies mc INNER JOIN (cast_info ci LEFT OUTER JOIN aka_name an ON an.person_id = ci.person_id) ON ci.movie_id = mc.movie_id) ON mc.company_id = cn.id) ON ci.movie_id = mk.movie_id)
WHERE (an.id % 1000 = 0 OR an.id IS NULL);
