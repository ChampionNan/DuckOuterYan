-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ci.role_id; predicate=hash(anchor) % 100 = 0
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM (char_name chn FULL OUTER JOIN (role_type rt FULL OUTER JOIN (cast_info ci FULL OUTER JOIN (title t FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id) ON t.id = ci.movie_id) ON rt.id = ci.role_id) ON chn.id = ci.role_id)
WHERE (t.production_year > 2005)
  AND hash(ci.role_id) % 100 = 0;
