-- source: SQLStorm v1.0/job/queries/15596.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Cast-credit coverage adapted from SQLStorm: a selected cast record is retained even when alternate-name or role metadata is absent.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=ci.person_id; group_key=a.person_id
SELECT a.person_id AS group_key, MAX(ci.person_id) AS max_key
FROM (((cast_info ci RIGHT OUTER JOIN aka_name a ON ci.person_id = a.person_id) FULL OUTER JOIN title t ON ci.movie_id = t.id) INNER JOIN role_type r ON ci.role_id = r.id)
WHERE ci.id % 1000 = 0
GROUP BY a.person_id;
