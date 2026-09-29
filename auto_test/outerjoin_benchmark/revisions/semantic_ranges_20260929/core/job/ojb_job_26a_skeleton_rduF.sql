-- source: JOB 26a
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (comp_cast_type cct1 RIGHT OUTER JOIN (comp_cast_type cct2 FULL OUTER JOIN (complete_cast cc LEFT OUTER JOIN (title t INNER JOIN cast_info ci ON t.id = ci.movie_id) ON t.id = cc.movie_id) ON cct2.id = cc.status_id) ON cct1.id = cc.subject_id)
WHERE t.production_year >= 2013;
