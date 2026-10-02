-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/5/forward
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src, R4.dst, R5.src
FROM ((((R2 R2 FULL OUTER JOIN R3 R3 ON R2.dst = R3.src) LEFT OUTER JOIN R4 R4 ON R3.dst = R4.src) RIGHT OUTER JOIN R5 R5 ON R4.dst = R5.src) INNER JOIN R1 R1 ON R1.dst = R2.src)
WHERE R1.src <= 2;
