-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (((((role_type r FULL OUTER JOIN cast_info ci ON ci.role_id = r.id) FULL OUTER JOIN title t ON ci.movie_id = t.id) FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id) FULL OUTER JOIN company_type c ON mc.company_type_id = c.id) FULL OUTER JOIN aka_name a ON a.person_id = ci.person_id)
WHERE a.id % 1000 = 0;
