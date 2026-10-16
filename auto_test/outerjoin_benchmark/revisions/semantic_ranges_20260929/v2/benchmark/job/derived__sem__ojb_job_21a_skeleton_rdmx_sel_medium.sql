-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: JOB 11a/21a release-year interval
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: job_release_period; tier=medium; JOB 11a/21a release-year interval
-- predicate: t.production_year BETWEEN 1950 AND 2000
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (movie_info mi LEFT OUTER JOIN (company_type ct INNER JOIN (title t FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON mc.company_type_id = ct.id) ON mi.movie_id = t.id)
WHERE t.production_year BETWEEN 1950 AND 2000;
