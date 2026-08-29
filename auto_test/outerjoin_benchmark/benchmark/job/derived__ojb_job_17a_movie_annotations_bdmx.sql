-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (((cast_info ci FULL OUTER JOIN title t ON t.id = ci.movie_id) FULL OUTER JOIN name n ON ci.person_id = n.id) FULL OUTER JOIN (keyword k FULL OUTER JOIN movie_keyword mk ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE t.id % 1000 = 0;
