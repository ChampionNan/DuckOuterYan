-- source: SQLStorm v1.0/job/queries/15596.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Cast-credit coverage adapted from SQLStorm: a selected cast record is retained even when alternate-name or role metadata is absent.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ci.person_id; group_key=a.person_id
SELECT COUNT(*) AS row_count
FROM (role_type r LEFT OUTER JOIN (title t INNER JOIN (aka_name a FULL OUTER JOIN cast_info ci ON ci.person_id = a.person_id) ON ci.movie_id = t.id) ON ci.role_id = r.id)
WHERE ci.id % 1000 = 0;
