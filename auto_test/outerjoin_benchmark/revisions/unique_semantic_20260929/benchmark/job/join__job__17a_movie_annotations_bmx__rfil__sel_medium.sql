-- query_type: join; family: job
-- source: JOB 17a
-- semantic_filter: job_person_name; tier=medium; JOB 17a person-name prefix search
-- predicate: n.name LIKE 'B%'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM ((title t INNER JOIN (movie_keyword mk LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id) RIGHT OUTER JOIN (cast_info ci FULL OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id)
WHERE n.name LIKE 'B%';
