-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILR; relation and predicate structure unchanged
SELECT * FROM ((R1 INNER JOIN R2 ON R1.dst=R2.src) LEFT OUTER JOIN (R3 RIGHT OUTER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src) WHERE R1.src % 3 = 0;
