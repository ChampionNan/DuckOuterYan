-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM (movie_companies mc INNER JOIN (role_type rt FULL OUTER JOIN (char_name chn RIGHT OUTER JOIN (cast_info ci LEFT OUTER JOIN title t ON t.id = ci.movie_id) ON chn.id = ci.role_id) ON rt.id = ci.role_id) ON t.id = mc.movie_id)
WHERE t.production_year > 2005;
