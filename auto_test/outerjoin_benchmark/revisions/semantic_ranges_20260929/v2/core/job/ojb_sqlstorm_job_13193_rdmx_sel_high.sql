-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: m.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (title m LEFT OUTER JOIN (role_type r INNER JOIN (aka_title a FULL OUTER JOIN (aka_name n RIGHT OUTER JOIN cast_info c ON c.person_id = n.person_id) ON c.movie_id = a.movie_id) ON c.role_id = r.id) ON a.id = m.id)
WHERE m.production_year >= 2001;
