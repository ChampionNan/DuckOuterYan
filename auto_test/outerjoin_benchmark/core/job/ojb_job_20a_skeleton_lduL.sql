-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; uniform left-deep LEFT OUTER JOIN control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 20a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((((complete_cast cc LEFT OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) LEFT OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) LEFT OUTER JOIN cast_info ci ON ci.movie_id = cc.movie_id) LEFT OUTER JOIN char_name chn ON chn.id = ci.person_role_id)
WHERE (cc.id % 1000 = 0 OR cc.id IS NULL);
