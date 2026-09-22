-- source: SQLStorm v1.0/job/queries/15596.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: Cast-credit coverage adapted from SQLStorm: a selected cast record is retained even when alternate-name or role metadata is absent.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=ci.person_id; predicate=hash(anchor) % 20 = 0
SELECT ci.id AS cast_id, a.name AS actor_name, t.title AS movie_title, ci.nr_order, r.role
FROM (role_type r FULL OUTER JOIN (aka_name a LEFT OUTER JOIN (cast_info ci RIGHT OUTER JOIN title t ON ci.movie_id = t.id) ON ci.person_id = a.person_id) ON ci.role_id = r.id)
WHERE (ci.id % 1000 = 0)
  AND hash(ci.person_id) % 20 = 0;
