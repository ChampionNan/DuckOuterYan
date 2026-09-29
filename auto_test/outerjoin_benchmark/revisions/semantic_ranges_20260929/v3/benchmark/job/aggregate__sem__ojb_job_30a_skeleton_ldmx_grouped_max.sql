-- source: JOB 30a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=cc.movie_id; group_key=t.id
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: t.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS group_key, MAX(cc.movie_id) AS max_key
FROM ((((complete_cast cc LEFT OUTER JOIN title t ON t.id = cc.movie_id) RIGHT OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) FULL OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) INNER JOIN cast_info ci ON t.id = ci.movie_id)
WHERE t.production_year >= 2008
GROUP BY t.id;
