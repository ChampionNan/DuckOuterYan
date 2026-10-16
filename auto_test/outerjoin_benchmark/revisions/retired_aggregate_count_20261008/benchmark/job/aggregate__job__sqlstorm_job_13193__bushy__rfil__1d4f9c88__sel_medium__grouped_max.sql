-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/13193.sql
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT n.person_id AS group_key, MAX(c.person_id) AS max_key
FROM (((cast_info c RIGHT OUTER JOIN aka_name n ON c.person_id = n.person_id) FULL OUTER JOIN role_type r ON c.role_id = r.id) INNER JOIN (title m LEFT OUTER JOIN aka_title a ON a.id = m.id) ON c.movie_id = a.movie_id)
WHERE m.production_year >= 2008
GROUP BY n.person_id;
