-- source: JOB 30a
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 30a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (movie_info mi FULL OUTER JOIN (cast_info ci RIGHT OUTER JOIN (comp_cast_type cct2 INNER JOIN (comp_cast_type cct1 LEFT OUTER JOIN complete_cast cc ON cct1.id = cc.subject_id) ON cct2.id = cc.status_id) ON ci.movie_id = cc.movie_id) ON ci.movie_id = mi.movie_id)
WHERE cc.id % 1000 = 0;
