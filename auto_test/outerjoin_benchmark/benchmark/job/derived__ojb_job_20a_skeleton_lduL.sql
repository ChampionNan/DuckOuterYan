-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 20a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((((char_name chn FULL OUTER JOIN cast_info ci ON chn.id = ci.role_id) FULL OUTER JOIN complete_cast cc ON ci.movie_id = cc.movie_id) FULL OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) FULL OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id)
WHERE cc.id % 1000 = 0;
