-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (((((aka_name a LEFT OUTER JOIN cast_info ci ON a.person_id = ci.person_id) FULL OUTER JOIN title t ON ci.movie_id = t.id) RIGHT OUTER JOIN movie_companies mc ON t.id = mc.movie_id) INNER JOIN company_type c ON mc.company_type_id = c.id) LEFT OUTER JOIN role_type r ON ci.role_id = r.id)
WHERE (a.id % 1000 = 0 OR a.id IS NULL);
