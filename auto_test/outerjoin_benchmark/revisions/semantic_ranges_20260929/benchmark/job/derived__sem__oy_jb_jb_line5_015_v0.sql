-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation graph retained; semantic filter replaced
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: t.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM title t
    INNER JOIN cast_info ci ON t.id = ci.movie_id
    LEFT OUTER JOIN role_type rt ON ci.role_id = rt.id
    RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    FULL OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE t.production_year >= 2008;
