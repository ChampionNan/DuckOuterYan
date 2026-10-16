-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 06a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id, ci.movie_id, mk.movie_id, k.id, mk.keyword_id, n.id, ci.person_id
FROM (name n FULL OUTER JOIN (keyword k RIGHT OUTER JOIN (movie_keyword mk LEFT OUTER JOIN (title t INNER JOIN cast_info ci ON t.id = ci.movie_id) ON t.id = mk.movie_id) ON k.id = mk.keyword_id) ON n.id = ci.person_id)
WHERE t.production_year >= 2013;
