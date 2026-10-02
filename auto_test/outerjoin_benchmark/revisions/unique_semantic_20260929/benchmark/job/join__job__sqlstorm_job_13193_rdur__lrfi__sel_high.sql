-- query_type: join; family: job
-- source: SQLStorm v1.0/job/queries/13193.sql
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: m.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (aka_name n LEFT OUTER JOIN (role_type r FULL OUTER JOIN (cast_info c RIGHT OUTER JOIN (aka_title a INNER JOIN title m ON a.id = m.id) ON c.movie_id = a.movie_id) ON c.role_id = r.id) ON c.person_id = n.person_id)
WHERE m.production_year >= 2001;
