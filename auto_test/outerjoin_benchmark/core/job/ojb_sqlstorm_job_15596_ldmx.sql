-- source: SQLStorm v1.0/job/queries/15596.sql
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: Cast-credit coverage adapted from SQLStorm: a selected cast record is retained even when alternate-name or role metadata is absent.
SELECT ci.id AS cast_id, a.name AS actor_name, t.title AS movie_title, ci.nr_order, r.role
FROM (((cast_info ci LEFT OUTER JOIN aka_name a ON ci.person_id = a.person_id) INNER JOIN title t ON ci.movie_id = t.id) LEFT OUTER JOIN role_type r ON ci.role_id = r.id)
WHERE ci.id % 1000 = 0;
