-- query_type: aggregate; family: job
-- source: SQLStorm v1.0/job/queries/13193.sql
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: m.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT n.person_id AS group_key, SUM(c.person_id) AS key_sum
FROM (title m LEFT OUTER JOIN (role_type r INNER JOIN (aka_title a FULL OUTER JOIN (aka_name n RIGHT OUTER JOIN cast_info c ON c.person_id = n.person_id) ON c.movie_id = a.movie_id) ON c.role_id = r.id) ON a.id = m.id)
WHERE m.production_year >= 2008
GROUP BY n.person_id;
