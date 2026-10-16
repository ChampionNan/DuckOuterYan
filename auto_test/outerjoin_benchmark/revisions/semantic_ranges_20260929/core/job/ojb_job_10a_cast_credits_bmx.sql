-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS title_id, t.title, ci.person_id, cn.name AS company_name, rt.role, mc.company_id
FROM ((title t INNER JOIN (movie_companies mc LEFT OUTER JOIN company_name cn ON cn.id = mc.company_id) ON t.id = mc.movie_id) RIGHT OUTER JOIN (cast_info ci FULL OUTER JOIN role_type rt ON rt.id = ci.role_id) ON t.id = ci.movie_id)
WHERE t.production_year >= 2013;
