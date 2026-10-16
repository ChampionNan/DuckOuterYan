-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 17a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (((title t LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) RIGHT OUTER JOIN (name n INNER JOIN cast_info ci ON ci.person_id = n.id) ON t.id = ci.movie_id)
WHERE n.name LIKE 'Ba%';
