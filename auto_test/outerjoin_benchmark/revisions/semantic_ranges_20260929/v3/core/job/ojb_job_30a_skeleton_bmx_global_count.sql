-- source: JOB 30a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=cc.movie_id; group_key=t.id
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: t.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM (((complete_cast cc LEFT OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) INNER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) FULL OUTER JOIN (title t RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id) ON t.id = cc.movie_id)
WHERE t.production_year >= 2008;
