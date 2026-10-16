-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=mc.movie_id; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM ((company_type ct FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN title t ON t.id = mc.movie_id) ON ct.id = mc.company_type_id) INNER JOIN (movie_info_idx mi_idx LEFT OUTER JOIN info_type it ON it.id = mi_idx.info_type_id) ON mc.movie_id = mi_idx.movie_id)
WHERE (ct.id % 1000 = 0)
  AND hash(mc.movie_id) % 1000 = 0;
