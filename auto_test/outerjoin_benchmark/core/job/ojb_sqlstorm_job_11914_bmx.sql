-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; cross-product-free bushy grouping with mixed join labeling
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM ((aka_name a LEFT OUTER JOIN (cast_info ci LEFT OUTER JOIN role_type r ON ci.role_id = r.id) ON a.person_id = ci.person_id) FULL OUTER JOIN (title t RIGHT OUTER JOIN (movie_companies mc INNER JOIN company_type c ON mc.company_type_id = c.id) ON t.id = mc.movie_id) ON ci.movie_id = t.id)
WHERE a.id % 1000 = 0;
