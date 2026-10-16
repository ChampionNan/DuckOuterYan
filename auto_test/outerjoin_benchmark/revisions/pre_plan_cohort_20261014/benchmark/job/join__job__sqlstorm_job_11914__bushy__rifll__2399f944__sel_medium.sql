-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/11914.sql
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT a.person_id, ci.person_id, ci.movie_id, t.id, mc.movie_id, mc.company_type_id, c.id, ci.role_id, r.id
FROM (((movie_companies mc RIGHT OUTER JOIN company_type c ON mc.company_type_id = c.id) INNER JOIN title t ON t.id = mc.movie_id) FULL OUTER JOIN (aka_name a LEFT OUTER JOIN (role_type r LEFT OUTER JOIN cast_info ci ON ci.role_id = r.id) ON a.person_id = ci.person_id) ON ci.movie_id = t.id)
WHERE t.production_year >= 2008;
