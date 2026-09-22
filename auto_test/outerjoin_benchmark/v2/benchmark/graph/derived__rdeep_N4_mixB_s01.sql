-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FIL; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FIL; relation and predicate structure unchanged
SELECT * FROM (R1 FULL OUTER JOIN (R2 INNER JOIN (R3 LEFT OUTER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src) ON R1.dst=R2.src) WHERE R1.src % 100 = 0;
