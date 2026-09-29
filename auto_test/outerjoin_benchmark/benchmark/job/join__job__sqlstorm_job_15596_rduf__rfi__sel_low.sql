-- query_type: join; family: job
-- source: SQLStorm v1.0/job/queries/15596.sql
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT ci.id AS cast_id, a.name AS actor_name, t.title AS movie_title, ci.nr_order, r.role
FROM (aka_name a RIGHT OUTER JOIN (title t FULL OUTER JOIN (cast_info ci INNER JOIN role_type r ON ci.role_id = r.id) ON ci.movie_id = t.id) ON ci.person_id = a.person_id)
WHERE t.production_year >= 2013;
