-- source: JOB 26a
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 26a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=cc.subject_id; predicate=hash(anchor) % 100 = 0
SELECT *
FROM (char_name chn FULL OUTER JOIN (cast_info ci FULL OUTER JOIN (comp_cast_type cct2 FULL OUTER JOIN (comp_cast_type cct1 FULL OUTER JOIN complete_cast cc ON cct1.id = cc.subject_id) ON cct2.id = cc.status_id) ON ci.movie_id = cc.movie_id) ON chn.id = ci.role_id)
WHERE (cc.id % 1000 = 0)
  AND hash(cc.subject_id) % 100 = 0;
