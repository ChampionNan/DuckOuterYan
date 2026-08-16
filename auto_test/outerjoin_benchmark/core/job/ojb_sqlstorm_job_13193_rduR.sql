-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; uniform right-deep RIGHT OUTER JOIN control
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (title m RIGHT OUTER JOIN (role_type r RIGHT OUTER JOIN (aka_title a RIGHT OUTER JOIN (aka_name n RIGHT OUTER JOIN cast_info c ON c.person_id = n.person_id) ON c.movie_id = a.movie_id) ON c.role_id = r.id) ON a.id = m.id)
WHERE (c.id % 1000 = 0 OR c.id IS NULL);
