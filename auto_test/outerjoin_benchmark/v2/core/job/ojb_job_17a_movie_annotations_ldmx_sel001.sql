-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=mk.movie_id; predicate=hash(anchor) % 1000 = 0
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM ((((title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) FULL OUTER JOIN name n ON ci.person_id = n.id) FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON mk.keyword_id = k.id)
WHERE (t.id % 1000 = 0)
  AND hash(mk.movie_id) % 1000 = 0;
