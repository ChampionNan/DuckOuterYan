-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM (movie_companies mc RIGHT OUTER JOIN (role_type rt INNER JOIN (char_name chn RIGHT OUTER JOIN (cast_info ci INNER JOIN title t ON t.id = ci.movie_id) ON chn.id = ci.person_role_id) ON rt.id = ci.role_id) ON t.id = mc.movie_id)
WHERE t.production_year > 2005;
