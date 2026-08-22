-- source: JOB 30a
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 30a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((((complete_cast cc RIGHT OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) INNER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) LEFT OUTER JOIN cast_info ci ON ci.movie_id = cc.movie_id) FULL OUTER JOIN movie_info mi ON ci.movie_id = mi.movie_id)
WHERE cc.id % 1000 = 0;
