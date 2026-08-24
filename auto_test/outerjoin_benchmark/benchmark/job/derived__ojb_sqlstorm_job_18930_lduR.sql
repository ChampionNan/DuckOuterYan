-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (((title m FULL OUTER JOIN aka_title t ON t.movie_id = m.id) FULL OUTER JOIN cast_info c ON c.movie_id = t.movie_id) FULL OUTER JOIN aka_name a ON a.person_id = c.person_id)
WHERE a.id % 1000 = 0;
