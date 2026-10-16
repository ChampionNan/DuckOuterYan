-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: m.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((title m FULL OUTER JOIN aka_title a ON a.id = m.id) LEFT OUTER JOIN ((aka_name n INNER JOIN cast_info c ON c.person_id = n.person_id) RIGHT OUTER JOIN role_type r ON c.role_id = r.id) ON c.movie_id = a.movie_id)
WHERE m.production_year >= 2008;
