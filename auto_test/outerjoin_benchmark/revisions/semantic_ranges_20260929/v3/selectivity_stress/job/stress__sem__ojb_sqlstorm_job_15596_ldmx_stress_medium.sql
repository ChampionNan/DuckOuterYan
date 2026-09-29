-- source: SQLStorm v1.0/job/queries/15596.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: films and episodes released since a given year
-- corpus_version: v3
-- derived_from_corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress_medium; 5–40% of the calibration population
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: t.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT ci.id AS cast_id, a.name AS actor_name, t.title AS movie_title, ci.nr_order, r.role
FROM (((cast_info ci RIGHT OUTER JOIN aka_name a ON ci.person_id = a.person_id) FULL OUTER JOIN title t ON ci.movie_id = t.id) INNER JOIN role_type r ON ci.role_id = r.id)
WHERE t.production_year >= 2008;
