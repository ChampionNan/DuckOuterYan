-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((info_type it RIGHT OUTER JOIN movie_info_idx mi_idx ON it.id = mi_idx.info_type_id) LEFT OUTER JOIN ((movie_companies mc INNER JOIN company_type ct ON ct.id = mc.company_type_id) FULL OUTER JOIN title t ON t.id = mc.movie_id) ON mc.movie_id = mi_idx.movie_id)
WHERE ct.id % 1000 = 0;
