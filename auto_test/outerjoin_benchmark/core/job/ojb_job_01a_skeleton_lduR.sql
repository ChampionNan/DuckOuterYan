-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((((title t FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id) FULL OUTER JOIN movie_info_idx mi_idx ON mc.movie_id = mi_idx.movie_id) FULL OUTER JOIN info_type it ON it.id = mi_idx.info_type_id) FULL OUTER JOIN company_type ct ON ct.id = mc.company_type_id)
WHERE ct.id % 1000 = 0;
