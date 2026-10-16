-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 16a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((((aka_name an LEFT OUTER JOIN cast_info ci ON an.person_id = ci.person_id) RIGHT OUTER JOIN movie_companies mc ON ci.movie_id = mc.movie_id) FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) INNER JOIN movie_keyword mk ON ci.movie_id = mk.movie_id)
WHERE an.id % 1000 = 0;
