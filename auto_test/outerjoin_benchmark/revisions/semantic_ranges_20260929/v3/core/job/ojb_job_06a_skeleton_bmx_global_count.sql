-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=mk.movie_id; group_key=t.id
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: t.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM ((cast_info ci RIGHT OUTER JOIN name n ON n.id = ci.person_id) FULL OUTER JOIN (title t INNER JOIN (movie_keyword mk LEFT OUTER JOIN keyword k ON k.id = mk.keyword_id) ON t.id = mk.movie_id) ON t.id = ci.movie_id)
WHERE t.production_year >= 2008;
