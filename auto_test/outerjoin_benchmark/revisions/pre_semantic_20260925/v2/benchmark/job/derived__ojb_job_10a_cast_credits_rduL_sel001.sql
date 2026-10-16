-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=ci.role_id; predicate=hash(anchor) % 1000 = 0
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM (char_name chn LEFT OUTER JOIN (role_type rt RIGHT OUTER JOIN (cast_info ci INNER JOIN (title t FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id) ON t.id = ci.movie_id) ON rt.id = ci.role_id) ON chn.id = ci.role_id)
WHERE (t.production_year > 2005)
  AND hash(ci.role_id) % 1000 = 0;
