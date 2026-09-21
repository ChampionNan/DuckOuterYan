-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=ci.role_id; predicate=hash(anchor) % 1000 = 0
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM (((char_name chn FULL OUTER JOIN cast_info ci ON chn.id = ci.role_id) FULL OUTER JOIN role_type rt ON rt.id = ci.role_id) FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN title t ON t.id = mc.movie_id) ON t.id = ci.movie_id)
WHERE (t.production_year > 2005)
  AND hash(ci.role_id) % 1000 = 0;
