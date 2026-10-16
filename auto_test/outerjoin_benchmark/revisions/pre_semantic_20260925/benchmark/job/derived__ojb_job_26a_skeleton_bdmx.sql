-- source: JOB 26a
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 26a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((char_name chn FULL OUTER JOIN cast_info ci ON chn.id = ci.role_id) RIGHT OUTER JOIN ((comp_cast_type cct1 INNER JOIN complete_cast cc ON cct1.id = cc.subject_id) LEFT OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) ON ci.movie_id = cc.movie_id)
WHERE cc.id % 1000 = 0;
