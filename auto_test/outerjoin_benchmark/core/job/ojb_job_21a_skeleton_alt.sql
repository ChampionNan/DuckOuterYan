-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; deterministic alternate mixed labeling; bushy grouping is structurally ineligible
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM ((((company_name cn FULL OUTER JOIN movie_companies mc ON mc.company_id = cn.id) RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) INNER JOIN movie_info mi ON mc.movie_id = mi.movie_id) LEFT OUTER JOIN movie_keyword mk ON mk.movie_id = mc.movie_id)
WHERE (cn.id % 1000 = 0 OR cn.id IS NULL);
