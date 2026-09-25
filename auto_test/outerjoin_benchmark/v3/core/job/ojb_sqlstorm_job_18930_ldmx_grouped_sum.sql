-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=t.movie_id; group_key=a.person_id
SELECT a.person_id AS group_key, SUM(t.movie_id) AS key_sum
FROM (((aka_name a RIGHT OUTER JOIN cast_info c ON a.person_id = c.person_id) FULL OUTER JOIN aka_title t ON c.movie_id = t.movie_id) INNER JOIN title m ON t.movie_id = m.id)
WHERE a.id % 1000 = 0
GROUP BY a.person_id;
