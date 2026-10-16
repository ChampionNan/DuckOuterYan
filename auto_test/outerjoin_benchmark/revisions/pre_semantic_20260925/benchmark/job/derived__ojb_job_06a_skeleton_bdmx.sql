-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM (((keyword k LEFT OUTER JOIN movie_keyword mk ON k.id = mk.keyword_id) FULL OUTER JOIN title t ON t.id = mk.movie_id) INNER JOIN (name n RIGHT OUTER JOIN cast_info ci ON n.id = ci.person_id) ON ci.movie_id = mk.movie_id)
WHERE ci.id % 1000 = 0;
