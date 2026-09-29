-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=c.person_id; group_key=n.person_id
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: m.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM (((cast_info c LEFT OUTER JOIN role_type r ON c.role_id = r.id) FULL OUTER JOIN aka_name n ON c.person_id = n.person_id) INNER JOIN (aka_title a RIGHT OUTER JOIN title m ON a.id = m.id) ON c.movie_id = a.movie_id)
WHERE m.production_year >= 2008;
