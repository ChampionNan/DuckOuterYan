-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: IL; relation graph retained; semantic filter replaced
-- semantic_filter: graph_source_range; tier=high; contiguous source-vertex interval
-- predicate: R1.src <= 306
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT * FROM (R1 INNER JOIN (R2 LEFT OUTER JOIN R3 ON R2.dst=R3.src) ON R1.dst=R2.src) WHERE R1.src <= 306;
