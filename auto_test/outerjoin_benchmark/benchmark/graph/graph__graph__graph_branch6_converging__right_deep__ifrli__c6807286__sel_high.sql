-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph branch/6/converging
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst, R5.dst, R6.dst
FROM (R6 R6 INNER JOIN (R5 R5 FULL OUTER JOIN (R4 R4 RIGHT OUTER JOIN (R3 R3 LEFT OUTER JOIN (R2 R2 INNER JOIN R1 R1 ON R1.dst = R2.dst) ON R2.dst = R3.dst) ON R2.dst = R4.dst) ON R3.dst = R5.dst) ON R3.dst = R6.dst)
WHERE R1.src <= 306;
