-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_revision: v1-mixed-20260922
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM ((title t LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id) RIGHT OUTER JOIN ((cast_info ci INNER JOIN role_type rt ON rt.id = ci.role_id) FULL OUTER JOIN char_name chn ON chn.id = ci.role_id) ON t.id = ci.movie_id)
WHERE t.production_year > 2005;
