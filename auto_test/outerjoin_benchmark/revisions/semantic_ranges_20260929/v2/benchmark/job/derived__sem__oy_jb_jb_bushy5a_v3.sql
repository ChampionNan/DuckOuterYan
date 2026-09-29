-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation and predicate structure unchanged
-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation graph retained; semantic filter replaced
-- semantic_filter: job_release_year; tier=high; films and episodes released since a given year
-- predicate: t.production_year >= 2001
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((( title t INNER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN ( movie_keyword mk FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE t.production_year >= 2001;
