-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (keyword k RIGHT OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN (name n INNER JOIN (cast_info ci INNER JOIN title t ON t.id = ci.movie_id) ON ci.person_id = n.id AND n.name LIKE 'B%') ON t.id = mk.movie_id) ON mk.keyword_id = k.id)
WHERE (t.id % 1000 = 0 OR t.id IS NULL);
