-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (aka_name a LEFT OUTER JOIN (company_type c INNER JOIN (movie_companies mc FULL OUTER JOIN (title t RIGHT OUTER JOIN (cast_info ci LEFT OUTER JOIN role_type r ON ci.role_id = r.id) ON ci.movie_id = t.id) ON t.id = mc.movie_id) ON mc.company_type_id = c.id) ON a.person_id = ci.person_id)
WHERE t.production_year >= 2013;
