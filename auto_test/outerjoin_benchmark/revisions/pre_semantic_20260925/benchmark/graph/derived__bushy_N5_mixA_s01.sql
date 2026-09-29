-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRFI; relation and predicate structure unchanged
SELECT * FROM (((R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src) RIGHT OUTER JOIN R3 ON R2.dst=R3.src) FULL OUTER JOIN (R4 INNER JOIN R5 ON R4.dst=R5.src) ON R3.dst=R4.src) WHERE R1.src % 100 = 0;
