-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/5/converging
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM ((SELECT src, dst FROM R3 WHERE src <= 40) R3 RIGHT OUTER JOIN ((SELECT src, dst FROM R4 WHERE src <= 40) R4 LEFT OUTER JOIN ((SELECT src, dst FROM R5 WHERE src <= 40) R5 INNER JOIN (R1 R1 FULL OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 40) R2 ON R1.dst = R2.dst) ON R1.dst = R5.dst) ON R1.dst = R4.dst) ON R1.dst = R3.dst)
WHERE R1.src <= 306;
