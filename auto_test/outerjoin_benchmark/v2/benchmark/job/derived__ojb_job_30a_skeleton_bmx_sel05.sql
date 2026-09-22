-- source: JOB 30a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 30a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=cc.subject_id; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (((complete_cast cc INNER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) FULL OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) LEFT OUTER JOIN (cast_info ci RIGHT OUTER JOIN movie_info mi ON ci.movie_id = mi.movie_id) ON ci.movie_id = cc.movie_id)
WHERE (cc.id % 1000 = 0)
  AND hash(cc.subject_id) % 20 = 0;
