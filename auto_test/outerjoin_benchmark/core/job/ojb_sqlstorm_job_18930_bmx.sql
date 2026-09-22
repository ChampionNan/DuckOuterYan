-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM ((aka_name a INNER JOIN cast_info c ON a.person_id = c.person_id) LEFT OUTER JOIN (aka_title t RIGHT OUTER JOIN title m ON t.movie_id = m.id) ON c.movie_id = t.movie_id)
WHERE a.id % 1000 = 0;
