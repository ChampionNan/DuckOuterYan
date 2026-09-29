-- corpus_revision: semantic-ranges-20260929
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILR; relation graph retained; semantic filter replaced
-- semantic_filter: graph_source_range; tier=low; contiguous source-vertex interval
-- predicate: R1.src <= 2
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT * FROM ((R1 INNER JOIN R2 ON R1.dst=R2.src) LEFT OUTER JOIN (R3 RIGHT OUTER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src) WHERE R1.src <= 2;
