-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; cross-product-free bushy grouping with mixed join labeling
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 20a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (((complete_cast cc LEFT OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) INNER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) FULL OUTER JOIN (cast_info ci RIGHT OUTER JOIN char_name chn ON chn.id = ci.person_role_id) ON ci.movie_id = cc.movie_id)
WHERE cc.id % 1000 = 0;
