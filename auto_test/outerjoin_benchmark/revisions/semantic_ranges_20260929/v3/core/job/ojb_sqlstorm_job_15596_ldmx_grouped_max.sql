-- source: SQLStorm v1.0/job/queries/15596.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=ci.person_id; group_key=a.person_id
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT a.person_id AS group_key, MAX(ci.person_id) AS max_key
FROM (((cast_info ci RIGHT OUTER JOIN aka_name a ON ci.person_id = a.person_id) FULL OUTER JOIN title t ON ci.movie_id = t.id) INNER JOIN role_type r ON ci.role_id = r.id)
WHERE t.production_year >= 2001
GROUP BY a.person_id;
