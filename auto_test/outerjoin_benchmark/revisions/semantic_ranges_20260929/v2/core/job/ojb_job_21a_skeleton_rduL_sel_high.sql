-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: JOB 11a/21a release-year interval
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: job_release_period; tier=high; JOB 11a/21a release-year interval
-- predicate: t.production_year BETWEEN 1950 AND 2010
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (company_name cn LEFT OUTER JOIN (company_type ct FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN (title t INNER JOIN movie_info mi ON mi.movie_id = t.id) ON t.id = mc.movie_id) ON mc.company_type_id = ct.id) ON mc.company_id = cn.id)
WHERE t.production_year BETWEEN 1950 AND 2010;
