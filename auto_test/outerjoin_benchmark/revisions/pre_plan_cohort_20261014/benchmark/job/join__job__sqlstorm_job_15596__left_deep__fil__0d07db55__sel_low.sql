-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/15596.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ci.id AS cast_id, a.name AS actor_name, t.title AS movie_title, ci.nr_order, r.role
FROM (((aka_name a FULL OUTER JOIN cast_info ci ON ci.person_id = a.person_id) INNER JOIN role_type r ON ci.role_id = r.id) LEFT OUTER JOIN title t ON ci.movie_id = t.id)
WHERE t.production_year >= 2013;
