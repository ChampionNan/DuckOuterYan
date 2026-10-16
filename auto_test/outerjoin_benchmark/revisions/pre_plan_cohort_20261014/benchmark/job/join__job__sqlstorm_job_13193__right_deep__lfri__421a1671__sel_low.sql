-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/13193.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c.person_id, n.person_id, c.movie_id, a.movie_id, c.role_id, r.id, a.id, m.id
FROM (title m LEFT OUTER JOIN (aka_title a FULL OUTER JOIN (role_type r RIGHT OUTER JOIN (cast_info c INNER JOIN aka_name n ON c.person_id = n.person_id) ON c.role_id = r.id) ON c.movie_id = a.movie_id) ON a.id = m.id)
WHERE m.production_year >= 2013;
