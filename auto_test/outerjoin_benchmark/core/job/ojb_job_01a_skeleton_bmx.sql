-- source: JOB 01a
-- transformation: connected join-subgraph adaptation; cross-product-free bushy grouping with mixed join labeling
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 01a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((company_type ct INNER JOIN (movie_companies mc RIGHT OUTER JOIN title t ON t.id = mc.movie_id) ON ct.id = mc.company_type_id) LEFT OUTER JOIN (movie_info_idx mi_idx FULL OUTER JOIN info_type it ON it.id = mi_idx.info_type_id) ON mc.movie_id = mi_idx.movie_id)
WHERE (ct.id % 1000 = 0 OR ct.id IS NULL);
