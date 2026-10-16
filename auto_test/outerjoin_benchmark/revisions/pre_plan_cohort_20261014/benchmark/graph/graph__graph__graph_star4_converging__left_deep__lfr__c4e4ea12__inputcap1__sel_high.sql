-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/4/converging
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst
FROM (((R1 R1 LEFT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 40) R2 ON R1.dst = R2.dst) FULL OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 40) R3 ON R1.dst = R3.dst) RIGHT OUTER JOIN (SELECT src, dst FROM R4 WHERE src <= 40) R4 ON R1.dst = R4.dst)
WHERE R1.src <= 306;
