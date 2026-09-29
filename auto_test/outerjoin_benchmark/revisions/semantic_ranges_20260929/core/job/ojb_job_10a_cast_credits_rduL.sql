-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS title_id, t.title, ci.person_id, cn.name AS company_name, rt.role, mc.company_id
FROM (role_type rt LEFT OUTER JOIN (cast_info ci INNER JOIN (title t RIGHT OUTER JOIN (movie_companies mc FULL OUTER JOIN company_name cn ON cn.id = mc.company_id) ON t.id = mc.movie_id) ON t.id = ci.movie_id) ON rt.id = ci.role_id)
WHERE t.production_year >= 2013;
