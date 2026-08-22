-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; cross-product-free bushy grouping with mixed join labeling
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM ((title t LEFT OUTER JOIN (movie_keyword mk LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id) INNER JOIN (cast_info ci INNER JOIN name n ON ci.person_id = n.id AND n.name LIKE 'B%') ON t.id = ci.movie_id)
WHERE t.id % 1000 = 0;
