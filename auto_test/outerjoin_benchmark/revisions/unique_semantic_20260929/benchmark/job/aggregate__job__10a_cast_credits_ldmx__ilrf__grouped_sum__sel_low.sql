-- query_type: aggregate; family: job
-- source: JOB 10a
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS group_key, SUM(mc.movie_id) AS key_sum
FROM ((((title t INNER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN role_type rt ON rt.id = ci.role_id) RIGHT OUTER JOIN movie_companies mc ON t.id = mc.movie_id) FULL OUTER JOIN company_name cn ON cn.id = mc.company_id)
WHERE t.production_year >= 2013
GROUP BY t.id;
