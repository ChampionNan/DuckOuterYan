-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
SELECT * FROM (R1 RIGHT OUTER JOIN (R2 FULL OUTER JOIN (R3 INNER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src) ON R1.dst=R2.src) WHERE R1.src % 20 = 0;
