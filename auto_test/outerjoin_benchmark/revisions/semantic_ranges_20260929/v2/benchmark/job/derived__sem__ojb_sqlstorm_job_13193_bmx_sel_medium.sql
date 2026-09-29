-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: m.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((cast_info c LEFT OUTER JOIN role_type r ON c.role_id = r.id) FULL OUTER JOIN aka_name n ON c.person_id = n.person_id) INNER JOIN (aka_title a RIGHT OUTER JOIN title m ON a.id = m.id) ON c.movie_id = a.movie_id)
WHERE m.production_year >= 2008;
