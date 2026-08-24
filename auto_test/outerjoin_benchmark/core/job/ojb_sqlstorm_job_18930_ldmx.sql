-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (((aka_name a FULL OUTER JOIN cast_info c ON a.person_id = c.person_id) FULL OUTER JOIN aka_title t ON c.movie_id = t.movie_id) FULL OUTER JOIN title m ON t.movie_id = m.id)
WHERE a.id % 1000 = 0;
