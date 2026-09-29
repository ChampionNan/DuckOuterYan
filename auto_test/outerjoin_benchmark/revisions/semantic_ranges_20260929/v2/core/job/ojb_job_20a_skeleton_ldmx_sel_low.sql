-- source: JOB 20a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((complete_cast cc LEFT OUTER JOIN title t ON t.id = cc.movie_id) RIGHT OUTER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) FULL OUTER JOIN comp_cast_type cct2 ON cct2.id = cc.status_id) INNER JOIN cast_info ci ON t.id = ci.movie_id)
WHERE t.production_year >= 2013;
