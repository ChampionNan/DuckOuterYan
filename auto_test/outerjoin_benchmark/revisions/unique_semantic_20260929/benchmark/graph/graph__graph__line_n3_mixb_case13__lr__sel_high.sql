-- query_type: graph; family: graph
-- source:
-- semantic_filter: graph_source_range; tier=high; contiguous source-vertex interval
-- predicate: R1.src <= 306
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT * FROM ((R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src) RIGHT OUTER JOIN R3 ON R2.dst=R3.src) WHERE R1.src <= 306;
