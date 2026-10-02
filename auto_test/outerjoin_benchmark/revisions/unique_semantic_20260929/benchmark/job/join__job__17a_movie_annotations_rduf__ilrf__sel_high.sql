-- query_type: join; family: job
-- source: JOB 17a
-- semantic_filter: job_person_name; tier=high; JOB 17a person-name prefix search
-- predicate: (n.name LIKE 'A%' OR n.name LIKE 'B%' OR n.name LIKE 'C%' OR n.name LIKE 'D%' OR n.name LIKE 'E%' OR n.name LIKE 'F%' OR n.name LIKE 'G%' OR n.name LIKE 'H%' OR n.name LIKE 'I%' OR n.name LIKE 'J%' OR n.name LIKE 'K%' OR n.name LIKE 'L%' OR n.name LIKE 'M%')
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (name n LEFT OUTER JOIN (cast_info ci INNER JOIN (title t RIGHT OUTER JOIN (movie_keyword mk FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id) ON t.id = ci.movie_id) ON ci.person_id = n.id)
WHERE (n.name LIKE 'A%' OR n.name LIKE 'B%' OR n.name LIKE 'C%' OR n.name LIKE 'D%' OR n.name LIKE 'E%' OR n.name LIKE 'F%' OR n.name LIKE 'G%' OR n.name LIKE 'H%' OR n.name LIKE 'I%' OR n.name LIKE 'J%' OR n.name LIKE 'K%' OR n.name LIKE 'L%' OR n.name LIKE 'M%');
