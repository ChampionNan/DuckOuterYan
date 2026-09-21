-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; cross-product-free bushy FULL-outer applicability form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=ci.person_id; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM ((aka_name a FULL OUTER JOIN (cast_info ci FULL OUTER JOIN role_type r ON ci.role_id = r.id) ON a.person_id = ci.person_id) FULL OUTER JOIN (title t FULL OUTER JOIN (movie_companies mc FULL OUTER JOIN company_type c ON mc.company_type_id = c.id) ON t.id = mc.movie_id) ON ci.movie_id = t.id)
WHERE (a.id % 1000 = 0)
  AND hash(ci.person_id) % 1000 = 0;
