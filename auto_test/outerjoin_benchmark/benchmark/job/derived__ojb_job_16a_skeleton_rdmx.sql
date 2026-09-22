-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 16a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM (movie_keyword mk LEFT OUTER JOIN (company_name cn INNER JOIN (movie_companies mc FULL OUTER JOIN (cast_info ci RIGHT OUTER JOIN aka_name an ON an.person_id = ci.person_id) ON ci.movie_id = mc.movie_id) ON mc.company_id = cn.id) ON ci.movie_id = mk.movie_id)
WHERE an.id % 1000 = 0;
