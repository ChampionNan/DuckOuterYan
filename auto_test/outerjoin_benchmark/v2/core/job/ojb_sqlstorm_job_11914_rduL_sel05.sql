-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=ci.person_id; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (aka_name a LEFT OUTER JOIN (company_type c INNER JOIN (movie_companies mc FULL OUTER JOIN (title t RIGHT OUTER JOIN (cast_info ci LEFT OUTER JOIN role_type r ON ci.role_id = r.id) ON ci.movie_id = t.id) ON t.id = mc.movie_id) ON mc.company_type_id = c.id) ON a.person_id = ci.person_id)
WHERE (a.id % 1000 = 0)
  AND hash(ci.person_id) % 20 = 0;
