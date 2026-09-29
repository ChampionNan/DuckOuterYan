-- query_type: aggregate; family: job
-- source: JOB 17a
-- semantic_filter: job_person_name; tier=medium; JOB 17a person-name prefix search
-- predicate: n.name LIKE 'B%'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM ((((title t INNER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON mk.keyword_id = k.id)
WHERE n.name LIKE 'B%';
