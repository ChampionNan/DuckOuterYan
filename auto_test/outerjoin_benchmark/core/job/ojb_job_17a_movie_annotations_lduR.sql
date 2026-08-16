-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; uniform left-deep RIGHT OUTER JOIN control
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM ((((title t RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id) RIGHT OUTER JOIN name n ON ci.person_id = n.id AND n.name LIKE 'B%') RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id)
WHERE (t.id % 1000 = 0 OR t.id IS NULL);
