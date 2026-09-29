-- source: JOB 06a
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((title t INNER JOIN cast_info ci ON t.id = ci.movie_id) FULL OUTER JOIN name n ON n.id = ci.person_id) LEFT OUTER JOIN (keyword k RIGHT OUTER JOIN movie_keyword mk ON k.id = mk.keyword_id) ON t.id = mk.movie_id)
WHERE t.production_year >= 2013;
