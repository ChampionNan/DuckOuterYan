-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 20a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=cc.subject_id; predicate=hash(anchor) % 100 = 0
SELECT *
FROM ((((complete_cast cc LEFT OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) RIGHT OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) FULL OUTER JOIN cast_info ci ON ci.movie_id = cc.movie_id) INNER JOIN char_name chn ON chn.id = ci.role_id)
WHERE (cc.id % 1000 = 0)
  AND hash(cc.subject_id) % 100 = 0;
