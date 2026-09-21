-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=mc.movie_id; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (company_type ct FULL OUTER JOIN (info_type it FULL OUTER JOIN (movie_info_idx mi_idx FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN title t ON t.id = mc.movie_id) ON mc.movie_id = mi_idx.movie_id) ON it.id = mi_idx.info_type_id) ON ct.id = mc.company_type_id)
WHERE (ct.id % 1000 = 0)
  AND hash(mc.movie_id) % 20 = 0;
