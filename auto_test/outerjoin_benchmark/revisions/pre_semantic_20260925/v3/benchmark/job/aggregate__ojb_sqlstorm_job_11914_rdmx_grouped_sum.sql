-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=ci.person_id; group_key=a.person_id
SELECT a.person_id AS group_key, SUM(ci.person_id) AS key_sum
FROM (role_type r RIGHT OUTER JOIN (company_type c LEFT OUTER JOIN (movie_companies mc INNER JOIN (title t FULL OUTER JOIN (cast_info ci RIGHT OUTER JOIN aka_name a ON a.person_id = ci.person_id) ON ci.movie_id = t.id) ON t.id = mc.movie_id) ON mc.company_type_id = c.id) ON ci.role_id = r.id)
WHERE a.id % 1000 = 0
GROUP BY a.person_id;
