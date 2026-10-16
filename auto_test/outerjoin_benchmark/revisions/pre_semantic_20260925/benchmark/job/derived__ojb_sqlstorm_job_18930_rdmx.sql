-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM (title m LEFT OUTER JOIN (aka_title t INNER JOIN (cast_info c FULL OUTER JOIN aka_name a ON a.person_id = c.person_id) ON c.movie_id = t.movie_id) ON t.movie_id = m.id)
WHERE a.id % 1000 = 0;
