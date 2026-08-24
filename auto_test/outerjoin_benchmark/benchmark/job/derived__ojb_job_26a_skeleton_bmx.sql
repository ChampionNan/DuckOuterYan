-- source: JOB 26a
-- transformation: connected join-subgraph adaptation; cross-product-free bushy FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 26a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (((complete_cast cc FULL OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) FULL OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) FULL OUTER JOIN (cast_info ci FULL OUTER JOIN char_name chn ON chn.id = ci.role_id) ON ci.movie_id = cc.movie_id)
WHERE cc.id % 1000 = 0;
