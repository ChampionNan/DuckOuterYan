-- query_type: graph; family: graph
-- source:
-- semantic_filter: graph_source_range; tier=low; contiguous source-vertex interval
-- predicate: R1.src <= 2
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT * FROM (R1 LEFT OUTER JOIN (R2 RIGHT OUTER JOIN R3 ON R2.dst=R3.src) ON R1.dst=R2.src) WHERE R1.src <= 2;
