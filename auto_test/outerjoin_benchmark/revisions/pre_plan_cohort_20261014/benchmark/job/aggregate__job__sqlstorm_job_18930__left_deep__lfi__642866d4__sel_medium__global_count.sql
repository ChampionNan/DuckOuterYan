-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/18930.sql
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM (((aka_name a LEFT OUTER JOIN cast_info c ON a.person_id = c.person_id) FULL OUTER JOIN aka_title t ON c.movie_id = t.movie_id) INNER JOIN title m ON t.movie_id = m.id)
WHERE m.production_year >= 2008;
