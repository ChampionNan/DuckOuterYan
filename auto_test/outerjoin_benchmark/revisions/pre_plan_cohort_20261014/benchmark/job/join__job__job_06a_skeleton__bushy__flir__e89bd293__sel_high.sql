-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 06a
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id, ci.movie_id, mk.movie_id, k.id, mk.keyword_id, n.id, ci.person_id
FROM (((movie_keyword mk FULL OUTER JOIN keyword k ON k.id = mk.keyword_id) LEFT OUTER JOIN title t ON t.id = mk.movie_id) INNER JOIN (cast_info ci RIGHT OUTER JOIN name n ON n.id = ci.person_id) ON t.id = ci.movie_id)
WHERE t.production_year >= 2001;
