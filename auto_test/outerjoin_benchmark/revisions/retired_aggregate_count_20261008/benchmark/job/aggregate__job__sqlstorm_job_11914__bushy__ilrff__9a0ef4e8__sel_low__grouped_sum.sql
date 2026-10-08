-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/11914.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT a.person_id AS group_key, SUM(ci.person_id) AS key_sum
FROM (((movie_companies mc INNER JOIN company_type c ON mc.company_type_id = c.id) LEFT OUTER JOIN title t ON t.id = mc.movie_id) RIGHT OUTER JOIN (aka_name a FULL OUTER JOIN (role_type r FULL OUTER JOIN cast_info ci ON ci.role_id = r.id) ON a.person_id = ci.person_id) ON ci.movie_id = t.id)
WHERE t.production_year >= 2013
GROUP BY a.person_id;
