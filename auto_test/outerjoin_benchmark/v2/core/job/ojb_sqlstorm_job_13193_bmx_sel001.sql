-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; cross-product-free bushy FULL-outer applicability form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=c.person_id; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM (((cast_info c FULL OUTER JOIN role_type r ON c.role_id = r.id) FULL OUTER JOIN aka_name n ON c.person_id = n.person_id) FULL OUTER JOIN (aka_title a FULL OUTER JOIN title m ON a.id = m.id) ON c.movie_id = a.movie_id)
WHERE (c.id % 1000 = 0)
  AND hash(c.person_id) % 1000 = 0;
