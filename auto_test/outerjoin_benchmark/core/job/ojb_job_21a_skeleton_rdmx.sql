-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 21a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM (movie_keyword mk LEFT OUTER JOIN (movie_info mi INNER JOIN (company_type ct FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON mc.company_type_id = ct.id) ON mc.movie_id = mi.movie_id) ON mk.movie_id = mc.movie_id)
WHERE cn.id % 1000 = 0;
