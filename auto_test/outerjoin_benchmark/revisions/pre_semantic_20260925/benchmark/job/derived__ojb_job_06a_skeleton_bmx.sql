-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((cast_info ci LEFT OUTER JOIN name n ON n.id = ci.person_id) FULL OUTER JOIN ((movie_keyword mk RIGHT OUTER JOIN title t ON t.id = mk.movie_id) INNER JOIN keyword k ON k.id = mk.keyword_id) ON ci.movie_id = mk.movie_id)
WHERE ci.id % 1000 = 0;
