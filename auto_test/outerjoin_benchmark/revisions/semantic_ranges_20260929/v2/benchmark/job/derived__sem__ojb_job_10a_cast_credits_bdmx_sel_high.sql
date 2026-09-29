-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS title_id, t.title, ci.person_id, cn.name AS company_name, rt.role, mc.company_id
FROM (((cast_info ci FULL OUTER JOIN title t ON t.id = ci.movie_id) INNER JOIN role_type rt ON rt.id = ci.role_id) LEFT OUTER JOIN (company_name cn RIGHT OUTER JOIN movie_companies mc ON cn.id = mc.company_id) ON t.id = mc.movie_id)
WHERE t.production_year >= 2001;
