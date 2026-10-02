-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph branch/6/forward
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R4.src, R3.dst, R5.src, R6.src
FROM (((R1 R1 INNER JOIN R2 R2 ON R1.dst = R2.src) RIGHT OUTER JOIN R4 R4 ON R2.dst = R4.src) FULL OUTER JOIN (R6 R6 INNER JOIN (R5 R5 LEFT OUTER JOIN R3 R3 ON R3.dst = R5.src) ON R3.dst = R6.src) ON R2.dst = R3.src)
WHERE R1.src <= 2;
