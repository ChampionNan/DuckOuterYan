-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_revision: v1-mixed-20260922
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM (char_name chn LEFT OUTER JOIN (role_type rt RIGHT OUTER JOIN (cast_info ci INNER JOIN (title t FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id) ON t.id = ci.movie_id) ON rt.id = ci.role_id) ON chn.id = ci.role_id)
WHERE t.production_year > 2005;
