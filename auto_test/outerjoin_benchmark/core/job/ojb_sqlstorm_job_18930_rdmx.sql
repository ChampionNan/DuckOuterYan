-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
SELECT *
FROM (title m INNER JOIN (aka_title t LEFT OUTER JOIN (cast_info c FULL OUTER JOIN aka_name a ON a.person_id = c.person_id) ON c.movie_id = t.movie_id) ON t.movie_id = m.id)
WHERE (a.id % 1000 = 0 OR a.id IS NULL);
