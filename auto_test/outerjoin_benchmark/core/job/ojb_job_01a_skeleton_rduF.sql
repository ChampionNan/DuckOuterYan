-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (company_type ct FULL OUTER JOIN (info_type it FULL OUTER JOIN (movie_info_idx mi_idx FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN title t ON t.id = mc.movie_id) ON mc.movie_id = mi_idx.movie_id) ON it.id = mi_idx.info_type_id) ON ct.id = mc.company_type_id)
WHERE ct.id % 1000 = 0;
