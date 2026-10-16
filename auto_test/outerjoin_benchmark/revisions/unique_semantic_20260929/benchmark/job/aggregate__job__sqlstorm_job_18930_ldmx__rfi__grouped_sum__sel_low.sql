-- query_type: aggregate; family: job
-- source: SQLStorm v1.0/job/queries/18930.sql
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: m.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT a.person_id AS group_key, SUM(t.movie_id) AS key_sum
FROM (((aka_name a RIGHT OUTER JOIN cast_info c ON a.person_id = c.person_id) FULL OUTER JOIN aka_title t ON c.movie_id = t.movie_id) INNER JOIN title m ON t.movie_id = m.id)
WHERE m.production_year >= 2013
GROUP BY a.person_id;
