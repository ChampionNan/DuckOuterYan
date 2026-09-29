-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((title m FULL OUTER JOIN aka_title a ON a.id = m.id) LEFT OUTER JOIN ((aka_name n INNER JOIN cast_info c ON c.person_id = n.person_id) RIGHT OUTER JOIN role_type r ON c.role_id = r.id) ON c.movie_id = a.movie_id)
WHERE c.id % 1000 = 0;
