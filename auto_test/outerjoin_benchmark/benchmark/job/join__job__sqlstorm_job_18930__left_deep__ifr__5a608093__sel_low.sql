-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/18930.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT a.person_id, c.person_id, c.movie_id, t.movie_id, m.id
FROM (((cast_info c INNER JOIN aka_title t ON c.movie_id = t.movie_id) FULL OUTER JOIN title m ON t.movie_id = m.id) RIGHT OUTER JOIN aka_name a ON a.person_id = c.person_id)
WHERE m.production_year >= 2013;
