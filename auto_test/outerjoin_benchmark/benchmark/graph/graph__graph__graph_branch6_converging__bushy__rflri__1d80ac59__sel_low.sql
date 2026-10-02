-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph branch/6/converging
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst, R5.dst, R6.dst
FROM (((R1 R1 RIGHT OUTER JOIN R2 R2 ON R1.dst = R2.dst) FULL OUTER JOIN R4 R4 ON R2.dst = R4.dst) LEFT OUTER JOIN (R6 R6 RIGHT OUTER JOIN (R5 R5 INNER JOIN R3 R3 ON R3.dst = R5.dst) ON R3.dst = R6.dst) ON R2.dst = R3.dst)
WHERE R1.src <= 2;
