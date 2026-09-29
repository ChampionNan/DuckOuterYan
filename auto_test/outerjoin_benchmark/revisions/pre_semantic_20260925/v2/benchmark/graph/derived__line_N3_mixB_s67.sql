-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FI; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RF; relation and predicate structure unchanged
SELECT * FROM ((R1 FULL OUTER JOIN R2 ON R1.dst=R2.src) INNER JOIN R3 ON R2.dst=R3.src) WHERE R1.src % 3 <> 0;
