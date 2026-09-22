-- source: SQLStorm v1.0/job/queries/18930.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=t.movie_id; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM ((title m FULL OUTER JOIN aka_title t ON t.movie_id = m.id) RIGHT OUTER JOIN (cast_info c LEFT OUTER JOIN aka_name a ON a.person_id = c.person_id) ON c.movie_id = t.movie_id)
WHERE (a.id % 1000 = 0)
  AND hash(t.movie_id) % 1000 = 0;
