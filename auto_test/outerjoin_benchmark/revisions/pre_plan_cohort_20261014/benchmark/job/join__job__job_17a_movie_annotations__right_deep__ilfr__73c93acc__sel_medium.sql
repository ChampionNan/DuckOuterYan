-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 17a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (keyword k INNER JOIN (movie_keyword mk LEFT OUTER JOIN (title t FULL OUTER JOIN (name n RIGHT OUTER JOIN cast_info ci ON ci.person_id = n.id) ON t.id = ci.movie_id) ON t.id = mk.movie_id) ON mk.keyword_id = k.id)
WHERE n.name LIKE 'B%';
