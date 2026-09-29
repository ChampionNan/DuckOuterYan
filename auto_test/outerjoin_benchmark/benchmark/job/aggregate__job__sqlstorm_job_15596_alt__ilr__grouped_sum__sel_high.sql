-- query_type: aggregate; family: job
-- source: SQLStorm v1.0/job/queries/15596.sql
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT a.person_id AS group_key, SUM(ci.person_id) AS key_sum
FROM (((cast_info ci INNER JOIN aka_name a ON ci.person_id = a.person_id) LEFT OUTER JOIN title t ON ci.movie_id = t.id) RIGHT OUTER JOIN role_type r ON ci.role_id = r.id)
WHERE t.production_year >= 2001
GROUP BY a.person_id;
