-- query_type: join; family: job
-- source: SQLStorm v1.0/job/queries/13193.sql
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: m.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((cast_info c LEFT OUTER JOIN aka_name n ON c.person_id = n.person_id) RIGHT OUTER JOIN aka_title a ON c.movie_id = a.movie_id) FULL OUTER JOIN role_type r ON c.role_id = r.id) INNER JOIN title m ON a.id = m.id)
WHERE m.production_year >= 2013;
