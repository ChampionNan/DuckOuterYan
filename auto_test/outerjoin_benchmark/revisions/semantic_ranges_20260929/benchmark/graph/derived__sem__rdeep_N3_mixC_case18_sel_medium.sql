-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RF; relation graph retained; semantic filter replaced
-- semantic_filter: graph_source_range; tier=medium; contiguous source-vertex interval
-- predicate: R1.src <= 83
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT * FROM (R1 RIGHT OUTER JOIN (R2 FULL OUTER JOIN R3 ON R2.dst=R3.src) ON R1.dst=R2.src) WHERE R1.src <= 83;
