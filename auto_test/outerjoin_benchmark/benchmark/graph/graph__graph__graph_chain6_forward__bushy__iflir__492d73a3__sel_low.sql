-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/6/forward
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src, R4.dst, R5.src, R5.dst, R6.src
FROM (((R5 R5 INNER JOIN R6 R6 ON R5.dst = R6.src) FULL OUTER JOIN R4 R4 ON R4.dst = R5.src) LEFT OUTER JOIN (R1 R1 INNER JOIN (R3 R3 RIGHT OUTER JOIN R2 R2 ON R2.dst = R3.src) ON R1.dst = R2.src) ON R3.dst = R4.src)
WHERE R1.src <= 2;
