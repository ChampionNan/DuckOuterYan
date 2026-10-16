-- query_type: join; family: job
-- source: JOB 11a
-- semantic_filter: job_release_period; tier=medium; JOB 11a/21a release-year interval
-- predicate: t.production_year BETWEEN 1950 AND 2000
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (company_name cn LEFT OUTER JOIN (company_type ct FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN (title t INNER JOIN movie_keyword mk ON t.id = mk.movie_id) ON t.id = mc.movie_id) ON mc.company_type_id = ct.id) ON mc.company_id = cn.id)
WHERE t.production_year BETWEEN 1950 AND 2000;
