-- query_type: graph; family: graph
-- source:
-- semantic_filter: graph_source_range; tier=medium; contiguous source-vertex interval
-- predicate: R1.src <= 83
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT * FROM (R1 LEFT OUTER JOIN (R2 RIGHT OUTER JOIN (R3 FULL OUTER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src) ON R1.dst=R2.src) WHERE R1.src <= 83;
