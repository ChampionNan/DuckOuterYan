-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; cross-product-free bushy FULL-outer applicability form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=t.movie_id; predicate=hash(anchor) % 100 = 0
SELECT *
FROM ((aka_name a FULL OUTER JOIN cast_info c ON a.person_id = c.person_id) FULL OUTER JOIN (aka_title t FULL OUTER JOIN title m ON t.movie_id = m.id) ON c.movie_id = t.movie_id)
WHERE (a.id % 1000 = 0)
  AND hash(t.movie_id) % 100 = 0;
