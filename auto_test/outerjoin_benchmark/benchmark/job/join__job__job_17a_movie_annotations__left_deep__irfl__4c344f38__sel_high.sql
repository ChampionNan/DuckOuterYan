-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 17a
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM ((((cast_info ci INNER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN title t ON t.id = ci.movie_id) FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id)
WHERE (n.name LIKE 'A%' OR n.name LIKE 'B%' OR n.name LIKE 'C%' OR n.name LIKE 'D%' OR n.name LIKE 'E%' OR n.name LIKE 'F%' OR n.name LIKE 'G%' OR n.name LIKE 'H%' OR n.name LIKE 'I%' OR n.name LIKE 'J%' OR n.name LIKE 'K%' OR n.name LIKE 'L%');
