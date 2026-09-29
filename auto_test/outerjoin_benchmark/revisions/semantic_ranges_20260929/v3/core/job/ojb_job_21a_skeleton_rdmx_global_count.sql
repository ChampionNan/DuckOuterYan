-- source: JOB 21a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: JOB 11a/21a release-year interval
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=mc.company_id; group_key=cn.id
-- semantic_filter: job_release_period; tier=high; JOB 11a/21a release-year interval
-- predicate: t.production_year BETWEEN 1950 AND 2010
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM (movie_info mi LEFT OUTER JOIN (company_type ct INNER JOIN (title t FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON mc.company_type_id = ct.id) ON mi.movie_id = t.id)
WHERE t.production_year BETWEEN 1950 AND 2010;
