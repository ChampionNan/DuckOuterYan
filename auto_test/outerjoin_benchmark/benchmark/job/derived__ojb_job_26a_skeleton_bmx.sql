-- source: JOB 26a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 26a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM (((complete_cast cc INNER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) FULL OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) LEFT OUTER JOIN (cast_info ci RIGHT OUTER JOIN char_name chn ON chn.id = ci.role_id) ON ci.movie_id = cc.movie_id)
WHERE cc.id % 1000 = 0;
