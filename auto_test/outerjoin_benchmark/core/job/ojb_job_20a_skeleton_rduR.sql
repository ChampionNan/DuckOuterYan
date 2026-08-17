-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; uniform right-deep RIGHT OUTER JOIN control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 20a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (char_name chn RIGHT OUTER JOIN (cast_info ci RIGHT OUTER JOIN (comp_cast_type cct2 RIGHT OUTER JOIN (comp_cast_type cct1 RIGHT OUTER JOIN complete_cast cc ON cct1.id = cc.subject_id) ON cct2.id = cc.status_id) ON ci.movie_id = cc.movie_id) ON chn.id = ci.person_role_id)
WHERE cc.id % 1000 = 0;
