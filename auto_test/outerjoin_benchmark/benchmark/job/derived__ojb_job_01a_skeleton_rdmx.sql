-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (title t FULL OUTER JOIN (info_type it FULL OUTER JOIN (movie_info_idx mi_idx FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN company_type ct ON ct.id = mc.company_type_id) ON mc.movie_id = mi_idx.movie_id) ON it.id = mi_idx.info_type_id) ON t.id = mc.movie_id)
WHERE ct.id % 1000 = 0;
