-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FIL; relation and predicate structure unchanged
SELECT * FROM ((R1 FULL OUTER JOIN R2 ON R1.dst=R2.src) INNER JOIN (R3 LEFT OUTER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src) WHERE R1.src % 5 = 0;
