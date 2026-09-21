-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ci.role_id; predicate=hash(anchor) % 100 = 0
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM ((((title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) FULL OUTER JOIN char_name chn ON chn.id = ci.role_id) FULL OUTER JOIN role_type rt ON rt.id = ci.role_id) FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id)
WHERE (t.production_year > 2005)
  AND hash(ci.role_id) % 100 = 0;
