-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_revision: v1-mixed-20260922
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM (((char_name chn INNER JOIN cast_info ci ON chn.id = ci.role_id) LEFT OUTER JOIN role_type rt ON rt.id = ci.role_id) FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN title t ON t.id = mc.movie_id) ON t.id = ci.movie_id)
WHERE t.production_year > 2005;
