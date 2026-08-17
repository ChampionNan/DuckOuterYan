-- source: JOB 10a
-- transformation: connected join-subgraph adaptation; cross-product-free bushy grouping with mixed join labeling
-- business_semantics: Movie-credit coverage: qualifying titles retain cast records while character, role, and company annotations may be absent.
SELECT t.id AS title_id, t.title, ci.person_id, chn.name AS character_name, rt.role, mc.company_id
FROM ((title t LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id) INNER JOIN ((cast_info ci INNER JOIN role_type rt ON rt.id = ci.role_id) LEFT OUTER JOIN char_name chn ON chn.id = ci.person_role_id) ON t.id = ci.movie_id)
WHERE t.production_year > 2005;
