-- query_type: join; family: job
-- source: JOB 11a
-- semantic_filter: job_release_period; tier=high; JOB 11a/21a release-year interval
-- predicate: t.production_year BETWEEN 1950 AND 2010
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((movie_keyword mk FULL OUTER JOIN title t ON t.id = mk.movie_id) LEFT OUTER JOIN ((movie_companies mc INNER JOIN company_name cn ON mc.company_id = cn.id) RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE t.production_year BETWEEN 1950 AND 2010;
