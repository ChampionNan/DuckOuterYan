-- source: SQLStorm v1.0/job/queries/13193.sql
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: A SQLStorm job query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=c.person_id; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (title m FULL OUTER JOIN (role_type r FULL OUTER JOIN (aka_title a FULL OUTER JOIN (aka_name n FULL OUTER JOIN cast_info c ON c.person_id = n.person_id) ON c.movie_id = a.movie_id) ON c.role_id = r.id) ON a.id = m.id)
WHERE (c.id % 1000 = 0)
  AND hash(c.person_id) % 20 = 0;
