-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: m.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (aka_name a RIGHT OUTER JOIN (cast_info c FULL OUTER JOIN (aka_title t INNER JOIN title m ON t.movie_id = m.id) ON c.movie_id = t.movie_id) ON a.person_id = c.person_id)
WHERE m.production_year >= 2001;
