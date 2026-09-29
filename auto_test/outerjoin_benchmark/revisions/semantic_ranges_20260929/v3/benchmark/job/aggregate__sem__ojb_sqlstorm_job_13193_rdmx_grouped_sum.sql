-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=c.person_id; group_key=n.person_id
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: m.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT n.person_id AS group_key, SUM(c.person_id) AS key_sum
FROM (title m LEFT OUTER JOIN (role_type r INNER JOIN (aka_title a FULL OUTER JOIN (aka_name n RIGHT OUTER JOIN cast_info c ON c.person_id = n.person_id) ON c.movie_id = a.movie_id) ON c.role_id = r.id) ON a.id = m.id)
WHERE m.production_year >= 2008
GROUP BY n.person_id;
