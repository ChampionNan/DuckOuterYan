-- source: SQLStorm v1.0/job/queries/15596.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ci.person_id; group_key=a.person_id
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM (role_type r LEFT OUTER JOIN (title t INNER JOIN (aka_name a FULL OUTER JOIN cast_info ci ON ci.person_id = a.person_id) ON ci.movie_id = t.id) ON ci.role_id = r.id)
WHERE t.production_year >= 2001;
