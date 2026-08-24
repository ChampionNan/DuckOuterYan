-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM ((((cast_info c FULL OUTER JOIN aka_name n ON c.person_id = n.person_id) FULL OUTER JOIN aka_title a ON c.movie_id = a.movie_id) FULL OUTER JOIN role_type r ON c.role_id = r.id) FULL OUTER JOIN title m ON a.id = m.id)
WHERE c.id % 1000 = 0;
