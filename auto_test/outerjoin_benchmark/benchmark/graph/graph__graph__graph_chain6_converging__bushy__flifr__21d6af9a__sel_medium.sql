-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/6/converging
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst, R5.dst, R6.dst
FROM (((R5 R5 FULL OUTER JOIN R6 R6 ON R5.dst = R6.dst) LEFT OUTER JOIN R4 R4 ON R4.dst = R5.dst) INNER JOIN (R1 R1 FULL OUTER JOIN (R3 R3 RIGHT OUTER JOIN R2 R2 ON R2.dst = R3.dst) ON R1.dst = R2.dst) ON R3.dst = R4.dst)
WHERE R1.src <= 83;
