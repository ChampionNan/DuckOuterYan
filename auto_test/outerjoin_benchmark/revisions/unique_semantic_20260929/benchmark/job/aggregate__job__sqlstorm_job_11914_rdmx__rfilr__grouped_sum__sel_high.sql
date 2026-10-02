-- query_type: aggregate; family: job
-- source: SQLStorm v1.0/job/queries/11914.sql
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT a.person_id AS group_key, SUM(ci.person_id) AS key_sum
FROM (role_type r RIGHT OUTER JOIN (company_type c LEFT OUTER JOIN (movie_companies mc INNER JOIN (title t FULL OUTER JOIN (cast_info ci RIGHT OUTER JOIN aka_name a ON a.person_id = ci.person_id) ON ci.movie_id = t.id) ON t.id = mc.movie_id) ON mc.company_type_id = c.id) ON ci.role_id = r.id)
WHERE t.production_year >= 2001
GROUP BY a.person_id;
