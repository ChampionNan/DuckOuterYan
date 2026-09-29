-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=c.person_id; group_key=n.person_id
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: m.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT n.person_id AS group_key, MAX(c.person_id) AS max_key
FROM ((((cast_info c LEFT OUTER JOIN aka_name n ON c.person_id = n.person_id) RIGHT OUTER JOIN aka_title a ON c.movie_id = a.movie_id) FULL OUTER JOIN role_type r ON c.role_id = r.id) INNER JOIN title m ON a.id = m.id)
WHERE m.production_year >= 2008
GROUP BY n.person_id;
