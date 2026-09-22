-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 20a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM (comp_cast_type cct1 LEFT OUTER JOIN (comp_cast_type cct2 RIGHT OUTER JOIN (complete_cast cc FULL OUTER JOIN (cast_info ci INNER JOIN char_name chn ON chn.id = ci.role_id) ON ci.movie_id = cc.movie_id) ON cct2.id = cc.status_id) ON cct1.id = cc.subject_id)
WHERE cc.id % 1000 = 0;
