-- source: JOB 30a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (cast_info ci LEFT OUTER JOIN (comp_cast_type cct2 INNER JOIN (comp_cast_type cct1 FULL OUTER JOIN (title t RIGHT OUTER JOIN complete_cast cc ON t.id = cc.movie_id) ON cct1.id = cc.subject_id) ON cct2.id = cc.status_id) ON t.id = ci.movie_id)
WHERE t.production_year >= 2013;
