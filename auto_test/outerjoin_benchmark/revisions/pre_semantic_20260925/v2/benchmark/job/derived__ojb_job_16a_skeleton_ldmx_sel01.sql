-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 16a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ci.movie_id; predicate=hash(anchor) % 100 = 0
SELECT *
FROM ((((aka_name an LEFT OUTER JOIN cast_info ci ON an.person_id = ci.person_id) RIGHT OUTER JOIN movie_companies mc ON ci.movie_id = mc.movie_id) FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) INNER JOIN movie_keyword mk ON ci.movie_id = mk.movie_id)
WHERE (an.id % 1000 = 0)
  AND hash(ci.movie_id) % 100 = 0;
