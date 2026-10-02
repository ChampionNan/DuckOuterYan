-- query_type: join; family: job
-- source: JOB 16a
-- semantic_filter: job_episode_range; tier=medium; JOB 16a episode-number interval
-- predicate: t.episode_nr >= 10 AND t.episode_nr < 100
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (company_name cn LEFT OUTER JOIN (movie_companies mc INNER JOIN (title t FULL OUTER JOIN (cast_info ci RIGHT OUTER JOIN aka_name an ON an.person_id = ci.person_id) ON ci.movie_id = t.id) ON t.id = mc.movie_id) ON mc.company_id = cn.id)
WHERE t.episode_nr >= 10 AND t.episode_nr < 100;
