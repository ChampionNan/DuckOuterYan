-- query_type: aggregate; family: job
-- source: SQLStorm v1.0/job/queries/11914.sql
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM (((((aka_name a LEFT OUTER JOIN cast_info ci ON a.person_id = ci.person_id) RIGHT OUTER JOIN title t ON ci.movie_id = t.id) FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id) INNER JOIN company_type c ON mc.company_type_id = c.id) LEFT OUTER JOIN role_type r ON ci.role_id = r.id)
WHERE t.production_year >= 2001;
