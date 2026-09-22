-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFIL; relation and predicate structure unchanged
SELECT * FROM ((R1 RIGHT OUTER JOIN R2 ON R1.dst=R2.src) FULL OUTER JOIN ((R3 INNER JOIN R4 ON R3.dst=R4.src) LEFT OUTER JOIN R5 ON R4.dst=R5.src) ON R2.dst=R3.src) WHERE R1.src % 100 = 0;
