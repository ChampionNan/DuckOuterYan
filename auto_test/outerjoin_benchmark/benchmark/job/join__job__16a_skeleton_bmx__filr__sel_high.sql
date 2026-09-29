-- query_type: join; family: job
-- source: JOB 16a
-- semantic_filter: job_episode_range; tier=high; JOB 16a episode-number interval
-- predicate: t.episode_nr >= 1 AND t.episode_nr <= 300
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((aka_name an FULL OUTER JOIN cast_info ci ON an.person_id = ci.person_id) INNER JOIN (title t LEFT OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON ci.movie_id = t.id)
WHERE t.episode_nr >= 1 AND t.episode_nr <= 300;
