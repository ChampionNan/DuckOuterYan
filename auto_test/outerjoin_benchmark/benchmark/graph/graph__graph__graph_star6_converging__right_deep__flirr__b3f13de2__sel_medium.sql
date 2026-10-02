-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/6/converging
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst, R5.dst, R6.dst
FROM (R3 R3 FULL OUTER JOIN (R4 R4 LEFT OUTER JOIN (R5 R5 INNER JOIN (R6 R6 RIGHT OUTER JOIN (R1 R1 RIGHT OUTER JOIN R2 R2 ON R1.dst = R2.dst) ON R1.dst = R6.dst) ON R1.dst = R5.dst) ON R1.dst = R4.dst) ON R1.dst = R3.dst)
WHERE R1.src <= 83;
