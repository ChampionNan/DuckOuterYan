-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: t.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((cast_info ci FULL OUTER JOIN title t ON t.id = ci.movie_id) INNER JOIN ((comp_cast_type cct1 LEFT OUTER JOIN complete_cast cc ON cct1.id = cc.subject_id) RIGHT OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) ON t.id = cc.movie_id)
WHERE t.production_year >= 2008;
