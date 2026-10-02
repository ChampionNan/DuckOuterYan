-- query_type: aggregate; family: job
-- source: JOB 16a
-- semantic_filter: job_episode_range; tier=low; JOB 16a episode-number interval
-- predicate: t.episode_nr >= 50 AND t.episode_nr < 100
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT an.person_id AS group_key, SUM(mc.movie_id) AS key_sum
FROM ((((aka_name an LEFT OUTER JOIN cast_info ci ON an.person_id = ci.person_id) RIGHT OUTER JOIN title t ON ci.movie_id = t.id) FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id) INNER JOIN company_name cn ON mc.company_id = cn.id)
WHERE t.episode_nr >= 50 AND t.episode_nr < 100
GROUP BY an.person_id;
