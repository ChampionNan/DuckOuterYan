-- source: SQLStorm v1.0/job/queries/15596.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT ci.id AS cast_id, a.name AS actor_name, t.title AS movie_title, ci.nr_order, r.role
FROM (role_type r FULL OUTER JOIN (aka_name a LEFT OUTER JOIN (cast_info ci RIGHT OUTER JOIN title t ON ci.movie_id = t.id) ON ci.person_id = a.person_id) ON ci.role_id = r.id)
WHERE t.production_year >= 2001;
