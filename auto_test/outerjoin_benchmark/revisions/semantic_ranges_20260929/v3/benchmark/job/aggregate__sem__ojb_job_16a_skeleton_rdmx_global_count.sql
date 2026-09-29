-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: JOB 16a episode-number interval
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=mc.movie_id; group_key=an.person_id
-- semantic_filter: job_episode_range; tier=low; JOB 16a episode-number interval
-- predicate: t.episode_nr >= 50 AND t.episode_nr < 100
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM (company_name cn LEFT OUTER JOIN (movie_companies mc INNER JOIN (title t FULL OUTER JOIN (cast_info ci RIGHT OUTER JOIN aka_name an ON an.person_id = ci.person_id) ON ci.movie_id = t.id) ON t.id = mc.movie_id) ON mc.company_id = cn.id)
WHERE t.episode_nr >= 50 AND t.episode_nr < 100;
