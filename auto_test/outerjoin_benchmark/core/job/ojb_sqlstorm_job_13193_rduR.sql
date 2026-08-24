-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (aka_name n FULL OUTER JOIN (role_type r FULL OUTER JOIN (cast_info c FULL OUTER JOIN (aka_title a FULL OUTER JOIN title m ON a.id = m.id) ON c.movie_id = a.movie_id) ON c.role_id = r.id) ON c.person_id = n.person_id)
WHERE c.id % 1000 = 0;
