-- source: JOB 16a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: JOB 16a episode-number interval
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: job_episode_range; tier=low; JOB 16a episode-number interval
-- predicate: t.episode_nr >= 50 AND t.episode_nr < 100
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((aka_name an FULL OUTER JOIN cast_info ci ON an.person_id = ci.person_id) INNER JOIN (title t LEFT OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON ci.movie_id = t.id)
WHERE t.episode_nr >= 50 AND t.episode_nr < 100;
