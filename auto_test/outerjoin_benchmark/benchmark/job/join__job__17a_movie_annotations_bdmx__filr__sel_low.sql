-- query_type: join; family: job
-- source: JOB 17a
-- semantic_filter: job_person_name; tier=low; JOB 17a person-name prefix search
-- predicate: n.name LIKE 'Ba%'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (((cast_info ci FULL OUTER JOIN title t ON t.id = ci.movie_id) INNER JOIN name n ON ci.person_id = n.id) LEFT OUTER JOIN (keyword k RIGHT OUTER JOIN movie_keyword mk ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE n.name LIKE 'Ba%';
