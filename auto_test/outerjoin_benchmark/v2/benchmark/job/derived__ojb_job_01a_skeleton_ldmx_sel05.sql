-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=mc.movie_id; predicate=hash(anchor) % 20 = 0
SELECT *
FROM ((((company_type ct LEFT OUTER JOIN movie_companies mc ON ct.id = mc.company_type_id) RIGHT OUTER JOIN movie_info_idx mi_idx ON mc.movie_id = mi_idx.movie_id) FULL OUTER JOIN info_type it ON it.id = mi_idx.info_type_id) INNER JOIN title t ON t.id = mc.movie_id)
WHERE (ct.id % 1000 = 0)
  AND hash(mc.movie_id) % 20 = 0;
