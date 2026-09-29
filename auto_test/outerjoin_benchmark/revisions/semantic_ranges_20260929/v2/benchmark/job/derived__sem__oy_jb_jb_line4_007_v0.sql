-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation graph retained; semantic filter replaced
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: t.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN aka_name an ON n.id = an.person_id
WHERE t.production_year >= 2008;
