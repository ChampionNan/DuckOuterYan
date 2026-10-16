-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Movie annotation coverage: title/cast/name records form the backbone, while keyword and company annotations are optional.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=mk.movie_id; predicate=hash(anchor) % 20 = 0
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (keyword k INNER JOIN (movie_keyword mk FULL OUTER JOIN (name n RIGHT OUTER JOIN (cast_info ci LEFT OUTER JOIN title t ON t.id = ci.movie_id) ON ci.person_id = n.id) ON t.id = mk.movie_id) ON mk.keyword_id = k.id)
WHERE (t.id % 1000 = 0)
  AND hash(mk.movie_id) % 20 = 0;
