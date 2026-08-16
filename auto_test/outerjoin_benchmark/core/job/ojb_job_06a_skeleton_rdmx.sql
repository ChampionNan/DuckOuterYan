-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: A movie-metadata coverage pattern extracted from JOB 06a; the source equality graph is retained while optionality is varied systematically.
SELECT *
FROM (title t INNER JOIN (name n LEFT OUTER JOIN (keyword k FULL OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN cast_info ci ON ci.movie_id = mk.movie_id) ON k.id = mk.keyword_id) ON n.id = ci.person_id) ON t.id = mk.movie_id)
WHERE (ci.id % 1000 = 0 OR ci.id IS NULL);
