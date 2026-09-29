-- source: JOB 11a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: JOB 11a/21a release-year interval
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=mc.company_id; group_key=cn.id
-- semantic_filter: job_release_period; tier=high; JOB 11a/21a release-year interval
-- predicate: t.production_year BETWEEN 1950 AND 2010
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cn.id AS group_key, MIN(mc.company_id) AS min_key
FROM ((((company_name cn LEFT OUTER JOIN movie_companies mc ON mc.company_id = cn.id) RIGHT OUTER JOIN title t ON t.id = mc.movie_id) FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) INNER JOIN movie_keyword mk ON t.id = mk.movie_id)
WHERE t.production_year BETWEEN 1950 AND 2010
GROUP BY cn.id;
