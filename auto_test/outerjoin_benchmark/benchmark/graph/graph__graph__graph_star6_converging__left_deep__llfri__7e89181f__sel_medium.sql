-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/6/converging
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst, R5.dst, R6.dst
FROM (((((R2 R2 LEFT OUTER JOIN R1 R1 ON R1.dst = R2.dst) LEFT OUTER JOIN R6 R6 ON R1.dst = R6.dst) FULL OUTER JOIN R5 R5 ON R1.dst = R5.dst) RIGHT OUTER JOIN R4 R4 ON R1.dst = R4.dst) INNER JOIN R3 R3 ON R1.dst = R3.dst)
WHERE R1.src <= 83;
