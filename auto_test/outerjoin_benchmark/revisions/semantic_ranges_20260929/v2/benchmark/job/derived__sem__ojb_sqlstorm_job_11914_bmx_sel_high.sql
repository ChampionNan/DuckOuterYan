-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((aka_name a FULL OUTER JOIN (cast_info ci FULL OUTER JOIN role_type r ON ci.role_id = r.id) ON a.person_id = ci.person_id) INNER JOIN (title t LEFT OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_type c ON mc.company_type_id = c.id) ON t.id = mc.movie_id) ON ci.movie_id = t.id)
WHERE t.production_year >= 2001;
