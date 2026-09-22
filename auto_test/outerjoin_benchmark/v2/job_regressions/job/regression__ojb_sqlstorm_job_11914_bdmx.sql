-- source: SQLStorm v1.0/job/queries/11914.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ci.person_id; predicate=hash(anchor) % 100 = 0
SELECT *
FROM ((((cast_info ci INNER JOIN aka_name a ON a.person_id = ci.person_id) INNER JOIN role_type r ON ci.role_id = r.id) LEFT OUTER JOIN title t ON ci.movie_id = t.id) RIGHT OUTER JOIN (company_type c FULL OUTER JOIN movie_companies mc ON mc.company_type_id = c.id) ON t.id = mc.movie_id)
WHERE (a.id % 1000 = 0)
  AND hash(ci.person_id) % 100 = 0;
