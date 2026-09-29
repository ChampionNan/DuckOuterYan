-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: m.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((aka_name a INNER JOIN cast_info c ON a.person_id = c.person_id) LEFT OUTER JOIN (aka_title t RIGHT OUTER JOIN title m ON t.movie_id = m.id) ON c.movie_id = t.movie_id)
WHERE m.production_year >= 2008;
