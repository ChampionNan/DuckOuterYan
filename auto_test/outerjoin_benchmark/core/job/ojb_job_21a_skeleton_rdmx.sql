-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (movie_keyword mk INNER JOIN (movie_info mi LEFT OUTER JOIN (company_type ct FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON mc.company_type_id = ct.id) ON mc.movie_id = mi.movie_id) ON mk.movie_id = mc.movie_id)
WHERE (cn.id % 1000 = 0 OR cn.id IS NULL);
