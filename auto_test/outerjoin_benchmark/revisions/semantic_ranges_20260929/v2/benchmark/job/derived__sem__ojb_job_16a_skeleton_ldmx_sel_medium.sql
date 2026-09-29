-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: JOB 16a episode-number interval
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: job_episode_range; tier=medium; JOB 16a episode-number interval
-- predicate: t.episode_nr >= 10 AND t.episode_nr < 100
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((aka_name an LEFT OUTER JOIN cast_info ci ON an.person_id = ci.person_id) RIGHT OUTER JOIN title t ON ci.movie_id = t.id) FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id) INNER JOIN company_name cn ON mc.company_id = cn.id)
WHERE t.episode_nr >= 10 AND t.episode_nr < 100;
