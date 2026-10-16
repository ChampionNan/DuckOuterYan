-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((((cast_info c LEFT OUTER JOIN aka_name n ON c.person_id = n.person_id) RIGHT OUTER JOIN aka_title a ON c.movie_id = a.movie_id) FULL OUTER JOIN role_type r ON c.role_id = r.id) INNER JOIN title m ON a.id = m.id)
WHERE c.id % 1000 = 0;
