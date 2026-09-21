-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 20a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=cc.subject_id; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM (comp_cast_type cct1 FULL OUTER JOIN (comp_cast_type cct2 FULL OUTER JOIN (complete_cast cc FULL OUTER JOIN (cast_info ci FULL OUTER JOIN char_name chn ON chn.id = ci.role_id) ON ci.movie_id = cc.movie_id) ON cct2.id = cc.status_id) ON cct1.id = cc.subject_id)
WHERE (cc.id % 1000 = 0)
  AND hash(cc.subject_id) % 1000 = 0;
