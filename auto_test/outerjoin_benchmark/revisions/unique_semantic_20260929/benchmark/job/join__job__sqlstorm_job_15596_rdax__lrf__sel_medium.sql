-- query_type: join; family: job
-- source: SQLStorm v1.0/job/queries/15596.sql
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: t.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT ci.id AS cast_id, a.name AS actor_name, t.title AS movie_title, ci.nr_order, r.role
FROM (role_type r FULL OUTER JOIN (aka_name a LEFT OUTER JOIN (cast_info ci RIGHT OUTER JOIN title t ON ci.movie_id = t.id) ON ci.person_id = a.person_id) ON ci.role_id = r.id)
WHERE t.production_year >= 2008;
