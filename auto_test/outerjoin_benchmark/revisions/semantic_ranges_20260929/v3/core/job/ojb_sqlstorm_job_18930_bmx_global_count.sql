-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=t.movie_id; group_key=a.person_id
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: m.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM ((aka_name a INNER JOIN cast_info c ON a.person_id = c.person_id) LEFT OUTER JOIN (aka_title t RIGHT OUTER JOIN title m ON t.movie_id = m.id) ON c.movie_id = t.movie_id)
WHERE m.production_year >= 2013;
