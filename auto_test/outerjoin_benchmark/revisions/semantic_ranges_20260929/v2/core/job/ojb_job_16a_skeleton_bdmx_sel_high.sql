-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: JOB 16a episode-number interval
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: job_episode_range; tier=high; JOB 16a episode-number interval
-- predicate: t.episode_nr >= 1 AND t.episode_nr <= 300
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((cast_info ci INNER JOIN aka_name an ON an.person_id = ci.person_id) LEFT OUTER JOIN title t ON ci.movie_id = t.id) RIGHT OUTER JOIN (company_name cn FULL OUTER JOIN movie_companies mc ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE t.episode_nr >= 1 AND t.episode_nr <= 300;
