-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 16a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT an.person_id, ci.person_id, ci.movie_id, t.id, mc.movie_id, mc.company_id, cn.id
FROM (((movie_companies mc LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id) RIGHT OUTER JOIN title t ON t.id = mc.movie_id) INNER JOIN (aka_name an FULL OUTER JOIN cast_info ci ON an.person_id = ci.person_id) ON ci.movie_id = t.id)
WHERE t.episode_nr >= 50 AND t.episode_nr < 100;
