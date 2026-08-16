-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (role_type r RIGHT OUTER JOIN (company_type c INNER JOIN (movie_companies mc LEFT OUTER JOIN (title t FULL OUTER JOIN (cast_info ci RIGHT OUTER JOIN aka_name a ON a.person_id = ci.person_id) ON ci.movie_id = t.id) ON t.id = mc.movie_id) ON mc.company_type_id = c.id) ON ci.role_id = r.id)
WHERE (a.id % 1000 = 0 OR a.id IS NULL);
