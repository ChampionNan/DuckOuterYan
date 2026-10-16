-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=mk.movie_id; predicate=hash(anchor) % 20 = 0
SELECT *
FROM ((cast_info ci LEFT OUTER JOIN name n ON n.id = ci.person_id) FULL OUTER JOIN ((movie_keyword mk RIGHT OUTER JOIN title t ON t.id = mk.movie_id) INNER JOIN keyword k ON k.id = mk.keyword_id) ON ci.movie_id = mk.movie_id)
WHERE (ci.id % 1000 = 0)
  AND hash(mk.movie_id) % 20 = 0;
