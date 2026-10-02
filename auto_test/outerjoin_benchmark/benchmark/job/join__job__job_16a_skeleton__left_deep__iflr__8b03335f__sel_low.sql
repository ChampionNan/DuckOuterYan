-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 16a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT an.person_id, ci.person_id, ci.movie_id, t.id, mc.movie_id, mc.company_id, cn.id
FROM ((((cast_info ci INNER JOIN title t ON ci.movie_id = t.id) FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id) LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id) RIGHT OUTER JOIN aka_name an ON an.person_id = ci.person_id)
WHERE t.episode_nr >= 50 AND t.episode_nr < 100;
