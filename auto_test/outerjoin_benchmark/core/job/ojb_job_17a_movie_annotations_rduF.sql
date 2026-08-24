-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (name n FULL OUTER JOIN (cast_info ci FULL OUTER JOIN (title t FULL OUTER JOIN (movie_keyword mk FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id) ON t.id = ci.movie_id) ON ci.person_id = n.id)
WHERE t.id % 1000 = 0;
