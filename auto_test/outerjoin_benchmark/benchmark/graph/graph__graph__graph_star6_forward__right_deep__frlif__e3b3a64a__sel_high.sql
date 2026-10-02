-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/6/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R3.src, R4.src, R5.src, R6.src
FROM (R6 R6 FULL OUTER JOIN (R5 R5 RIGHT OUTER JOIN (R4 R4 LEFT OUTER JOIN (R3 R3 INNER JOIN (R2 R2 FULL OUTER JOIN R1 R1 ON R1.dst = R2.src) ON R1.dst = R3.src) ON R1.dst = R4.src) ON R1.dst = R5.src) ON R1.dst = R6.src)
WHERE R1.src <= 306;
