-- query_type: aggregate; family: job
-- source: JOB 11a
-- semantic_filter: job_release_period; tier=high; JOB 11a/21a release-year interval
-- predicate: t.production_year BETWEEN 1950 AND 2010
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cn.id AS group_key, MAX(mc.company_id) AS max_key
FROM (movie_keyword mk LEFT OUTER JOIN (company_type ct INNER JOIN (title t FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON mc.company_type_id = ct.id) ON t.id = mk.movie_id)
WHERE t.production_year BETWEEN 1950 AND 2010
GROUP BY cn.id;
