-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: JOB 11a/21a release-year interval
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: job_release_period; tier=low; JOB 11a/21a release-year interval
-- predicate: t.production_year BETWEEN 1999 AND 2000
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((company_name cn LEFT OUTER JOIN movie_companies mc ON mc.company_id = cn.id) RIGHT OUTER JOIN title t ON t.id = mc.movie_id) FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) INNER JOIN movie_info mi ON mi.movie_id = t.id)
WHERE t.production_year BETWEEN 1999 AND 2000;
