-- query_type: join; family: job
-- source: SQLStorm v1.0/job/queries/18930.sql
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: m.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (title m LEFT OUTER JOIN (aka_title t INNER JOIN (cast_info c FULL OUTER JOIN aka_name a ON a.person_id = c.person_id) ON c.movie_id = t.movie_id) ON t.movie_id = m.id)
WHERE m.production_year >= 2013;
