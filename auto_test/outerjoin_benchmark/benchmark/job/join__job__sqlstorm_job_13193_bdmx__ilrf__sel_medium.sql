-- query_type: join; family: job
-- source: SQLStorm v1.0/job/queries/13193.sql
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: m.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((title m FULL OUTER JOIN aka_title a ON a.id = m.id) LEFT OUTER JOIN ((aka_name n INNER JOIN cast_info c ON c.person_id = n.person_id) RIGHT OUTER JOIN role_type r ON c.role_id = r.id) ON c.movie_id = a.movie_id)
WHERE m.production_year >= 2008;
