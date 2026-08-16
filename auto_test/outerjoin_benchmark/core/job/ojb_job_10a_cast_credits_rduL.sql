-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; uniform right-deep LEFT OUTER JOIN control
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM (movie_companies mc LEFT OUTER JOIN (role_type rt LEFT OUTER JOIN (char_name chn LEFT OUTER JOIN (cast_info ci LEFT OUTER JOIN title t ON t.id = ci.movie_id) ON chn.id = ci.person_role_id) ON rt.id = ci.role_id) ON t.id = mc.movie_id)
WHERE (t.production_year > 2005 OR t.id IS NULL);
