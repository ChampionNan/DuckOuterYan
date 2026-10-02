-- query_type: graph; family: graph
-- source:
-- semantic_filter: graph_source_range; tier=medium; contiguous source-vertex interval
-- predicate: R1.src <= 83
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT * FROM (((R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src) RIGHT OUTER JOIN R3 ON R2.dst=R3.src) FULL OUTER JOIN (R4 INNER JOIN R5 ON R4.dst=R5.src) ON R3.dst=R4.src) WHERE R1.src <= 83;
