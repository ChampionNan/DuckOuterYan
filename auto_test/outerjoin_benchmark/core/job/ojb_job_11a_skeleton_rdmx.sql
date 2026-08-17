-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 11a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (keyword k RIGHT OUTER JOIN (movie_keyword mk INNER JOIN (company_type ct LEFT OUTER JOIN (movie_companies mc FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) ON mc.company_type_id = ct.id) ON mk.movie_id = mc.movie_id) ON mk.keyword_id = k.id)
WHERE cn.id % 1000 = 0;
