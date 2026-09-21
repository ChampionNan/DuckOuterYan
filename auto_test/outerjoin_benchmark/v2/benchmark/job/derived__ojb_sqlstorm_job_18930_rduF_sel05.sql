-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=t.movie_id; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (aka_name a FULL OUTER JOIN (cast_info c FULL OUTER JOIN (aka_title t FULL OUTER JOIN title m ON t.movie_id = m.id) ON c.movie_id = t.movie_id) ON a.person_id = c.person_id)
WHERE (a.id % 1000 = 0)
  AND hash(t.movie_id) % 20 = 0;
